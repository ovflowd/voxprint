"""The tee against Home Assistant's real SpeechToTextEntity, without a running Home Assistant.

The fake engine implements only async_process_audio_stream, like most STT integrations, so each call
goes through the base class's own methods: internal_async_process_audio_stream, then
internal_async_process_audio_stream_with_progress (the tee), then async_process_audio_stream_with_progress.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
import time
from typing import Any

from homeassistant.components import stt
import pytest

from custom_components.voxprint import tee
from fakes import META, FakeSTT

CHUNK = b"\x01\x02" * 160


class Engine(FakeSTT):
    """An engine that can fail, stop reading early, or take a while to transcribe, without a running Home Assistant."""

    def __init__(self, fail: bool = False, stop_after: int | None = None, finalise: float = 0.0) -> None:
        self.fail, self.stop_after, self.finalise, self.got = fail, stop_after, finalise, 0
        self.entity_id = "stt.engine"

    def async_write_ha_state(self) -> None:
        pass

    async def async_process_audio_stream(
        self, metadata: stt.SpeechMetadata, stream: AsyncIterator[bytes]
    ) -> stt.SpeechResult:
        async for chunk in stream:
            self.got += len(chunk)
            if self.fail:
                raise RuntimeError("engine failed")
            if self.stop_after and self.got >= self.stop_after:
                break
        await asyncio.sleep(self.finalise)
        return stt.SpeechResult("hello", stt.SpeechResultState.SUCCESS)


class Hooks:
    def __init__(self, start: Callable[[Any], tee.Capture | None] | None = None, end_fails: bool = False) -> None:
        self.start = start or (lambda metadata: tee.Capture("assist_satellite.test", 1))
        self.end_fails = end_fails
        self.ended: list[tuple[int, bool, float]] = []

    def on_start(self, metadata: Any) -> tee.Capture | None:
        return self.start(metadata)

    def on_end(self, cap: tee.Capture) -> None:
        self.ended.append((len(cap.buf), cap.capturing, time.perf_counter()))
        if self.end_fails:
            raise ValueError("end")

    def install(self, engine: Engine) -> None:
        assert tee.install(engine, self.on_start, self.on_end)


async def chunks(n: int, delay: float = 0.0) -> AsyncIterator[bytes]:
    for _ in range(n):
        await asyncio.sleep(delay)
        yield CHUNK


async def run(engine: Engine, n: int) -> stt.SpeechResult:
    return await engine.internal_async_process_audio_stream(META, chunks(n))


def test_the_base_class_still_has_the_method_the_tee_shadows() -> None:
    assert tee.supported(stt.SpeechToTextEntity)


async def test_the_tee_passes_every_byte_and_the_result_through() -> None:
    engine, hooks = Engine(), Hooks()
    hooks.install(engine)
    result = await run(engine, 300)
    assert result.text == "hello"
    assert result.result == stt.SpeechResultState.SUCCESS
    assert engine.got == 300 * len(CHUNK)
    assert [(size, capturing) for size, capturing, _ in hooks.ended] == [(300 * len(CHUNK), True)]


async def test_scoring_can_start_before_the_engine_returns() -> None:
    engine, hooks = Engine(finalise=0.3), Hooks()
    hooks.install(engine)
    await run(engine, 100)
    assert time.perf_counter() - hooks.ended[0][2] >= 0.25


async def test_an_engine_that_stops_reading_early_still_gets_scored_once() -> None:
    engine, hooks = Engine(stop_after=100 * len(CHUNK)), Hooks()
    hooks.install(engine)
    result = await run(engine, 300)
    assert result.text == "hello"
    assert [size for size, _, _ in hooks.ended] == [engine.got]


async def test_engine_errors_reach_the_pipeline_unchanged() -> None:
    engine, hooks = Engine(fail=True), Hooks()
    hooks.install(engine)
    with pytest.raises(RuntimeError, match="engine failed"):
        await run(engine, 10)
    assert len(hooks.ended) == 1


async def test_a_failing_start_hook_passes_the_audio_through() -> None:
    def broken(metadata: Any) -> tee.Capture:
        raise ValueError("start")

    engine, hooks = Engine(), Hooks(start=broken)
    hooks.install(engine)
    result = await run(engine, 50)
    assert result.text == "hello"
    assert engine.got == 50 * len(CHUNK)
    assert hooks.ended == []


async def test_audio_nobody_claims_passes_through_uncaptured() -> None:
    engine, hooks = Engine(), Hooks(start=lambda metadata: None)
    hooks.install(engine)
    result = await run(engine, 50)
    assert result.text == "hello"
    assert hooks.ended == []


async def test_a_failing_end_hook_does_not_touch_the_result() -> None:
    engine, hooks = Engine(), Hooks(end_fails=True)
    hooks.install(engine)
    result = await run(engine, 50)
    assert result.text == "hello"


async def test_capture_stops_at_15_seconds_while_the_engine_gets_everything() -> None:
    engine, hooks = Engine(), Hooks()
    hooks.install(engine)
    await run(engine, 1700)
    assert engine.got == 1700 * len(CHUNK)
    size, capturing, _ = hooks.ended[0]
    assert size <= tee.MAX_BYTES
    assert capturing is False


async def test_cancellation_reaches_the_pipeline_and_the_capture_is_closed() -> None:
    engine, hooks = Engine(), Hooks()
    hooks.install(engine)
    task = asyncio.create_task(engine.internal_async_process_audio_stream(META, chunks(1000, delay=0.01)))
    await asyncio.sleep(0.1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(hooks.ended) == 1


async def test_uninstall_brings_the_class_method_back() -> None:
    engine, hooks = Engine(), Hooks()
    hooks.install(engine)
    assert tee.is_installed(engine)
    tee.uninstall(engine)
    assert not tee.is_installed(engine)
    assert tee.PATCHED_ATTR not in engine.__dict__
    result = await run(engine, 10)
    assert result.text == "hello"
    assert hooks.ended == []


async def test_installing_twice_keeps_one_tee() -> None:
    engine, hooks = Engine(), Hooks()
    hooks.install(engine)
    first = engine.__dict__[tee.PATCHED_ATTR]
    hooks.install(engine)
    assert engine.__dict__[tee.PATCHED_ATTR] is first


def test_an_object_without_the_method_cannot_take_a_tee() -> None:
    assert not tee.install(object(), lambda m: None, lambda c: None)


class Renamed(Engine):
    async def internal_async_process_audio_stream_with_progress(  # type: ignore[override]
        self, meta: stt.SpeechMetadata, audio: AsyncIterator[bytes]
    ) -> AsyncIterator[Any]:
        yield stt.SpeechResult("hello", stt.SpeechResultState.SUCCESS)


class Extended(Engine):
    """A later Home Assistant that adds a parameter to the method the tee shadows."""

    extra: Any = None

    async def internal_async_process_audio_stream_with_progress(  # type: ignore[override]
        self, metadata: stt.SpeechMetadata, stream: AsyncIterator[bytes], extra: Any = None
    ) -> AsyncIterator[Any]:
        self.extra = extra
        async for chunk in stream:
            self.got += len(chunk)
        yield stt.SpeechResult("hello", stt.SpeechResultState.SUCCESS)


def test_a_method_with_other_parameters_is_left_alone() -> None:
    assert not tee.supported(Renamed)
    assert not tee.install(Renamed(), lambda m: None, lambda c: None)


async def test_a_new_parameter_reaches_the_engine_and_the_audio_is_still_captured() -> None:
    engine, hooks = Extended(), Hooks()
    hooks.install(engine)
    results = [r async for r in engine.internal_async_process_audio_stream_with_progress(META, chunks(10), extra=1)]
    assert results[0].text == "hello"
    assert engine.extra == 1
    assert engine.got == 10 * len(CHUNK)
    assert [size for size, _, _ in hooks.ended] == [10 * len(CHUNK)]


async def test_arguments_the_tee_cannot_read_pass_through_uncaptured() -> None:
    engine, hooks = Extended(), Hooks()
    hooks.install(engine)
    with pytest.raises(TypeError):
        [r async for r in engine.internal_async_process_audio_stream_with_progress(META, chunks(1), 1, 2)]
    assert hooks.ended == []
