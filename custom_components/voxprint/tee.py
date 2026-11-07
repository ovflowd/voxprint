"""Copy the audio an STT entity receives without changing what the entity does.

The Assist pipeline calls `entity.internal_async_process_audio_stream()` (homeassistant/components/stt/entity.py),
which iterates `self.internal_async_process_audio_stream_with_progress()`. Shadowing that second method on one
entity instance puts a tee in front of the real engine: each chunk is passed on unchanged and also appended to a
buffer in RAM.

The tee fails open:
- It takes any arguments and hands them on unchanged, so a new parameter in a later Home Assistant reaches the
  engine. If `metadata` and `stream` can't be found among them, nothing is captured.
- If `on_start` raises or returns None, the call goes straight to the original and nothing is captured.
- A capture error or the size cap only stops the capture, never the stream.
- Results and exceptions of the original pass through untouched.
- `on_end` runs once per capture, when the audio ends or the engine stops reading, and never raises into the
  stream.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterable, Callable
from contextlib import aclosing
import inspect
import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)

PATCHED_ATTR = "internal_async_process_audio_stream_with_progress"
MARK = "_voxprint_tee"
PARAMETERS = ("metadata", "stream")
# The pipeline's own utterance cap: 15 s of s16le mono at 16 kHz.
MAX_BYTES = 15 * 16000 * 2


class Capture:
    """The audio of one utterance, in RAM only."""

    __slots__ = ("buf", "capturing", "ended", "enrolling", "satellite", "seq")

    def __init__(self, satellite: str, seq: int, enrolling: str | None = None) -> None:
        self.buf = bytearray()
        self.capturing = True
        self.ended = False
        self.enrolling = enrolling
        self.satellite = satellite
        self.seq = seq


def supported(entity_class: type) -> bool:
    """Whether the class still has the stream method, taking `metadata` and `stream`."""
    method = getattr(entity_class, PATCHED_ATTR, None)
    if not callable(method):
        return False
    try:
        parameters = inspect.signature(method).parameters
    except TypeError, ValueError:
        return False
    return all(name in parameters for name in PARAMETERS)


def is_installed(entity: Any) -> bool:
    return getattr(getattr(entity, "__dict__", {}).get(PATCHED_ATTR), MARK, False)


def _end(cap: Capture, on_end: Callable[[Capture], None]) -> None:
    if cap.ended:
        return
    cap.ended = True
    try:
        on_end(cap)
    except Exception:
        _LOGGER.exception("Voxprint couldn't score this utterance")


async def _copy(source: AsyncIterable[bytes], cap: Capture, on_end: Callable[[Capture], None]) -> AsyncGenerator[bytes]:
    async for chunk in source:
        if cap.capturing:
            try:
                if len(cap.buf) + len(chunk) <= MAX_BYTES:
                    cap.buf += chunk
                else:
                    cap.capturing = False
            except Exception:
                cap.capturing = False
        yield chunk
    # The speaker stopped: scoring can start while the engine is still transcribing.
    _end(cap, on_end)


def install(entity: Any, on_start: Callable[[Any], Capture | None], on_end: Callable[[Capture], None]) -> bool:
    """Shadow the entity's stream method with a tee. Returns False if the entity can't take one."""
    if is_installed(entity):
        return True
    original = getattr(entity, PATCHED_ATTR, None)
    if original is None or not hasattr(entity, "__dict__") or not supported(type(entity)):
        _LOGGER.warning("%s has no %s(metadata, stream); Voxprint can't hear it", entity, PATCHED_ATTR)
        return False
    signature = inspect.signature(original)

    async def tee_with_progress(*args: Any, **kwargs: Any) -> AsyncGenerator[Any]:
        cap = None
        try:
            bound = signature.bind(*args, **kwargs)
            cap = on_start(bound.arguments["metadata"])
        except Exception:
            _LOGGER.exception("Voxprint couldn't take this stream; passing the audio through")
        if cap is not None:
            bound.arguments["stream"] = _copy(bound.arguments["stream"], cap, on_end)
            args, kwargs = bound.args, bound.kwargs
        try:
            async with aclosing(original(*args, **kwargs)) as results:
                async for result in results:
                    yield result
        finally:
            # Also on engine errors, cancellation and an engine that stopped reading early; those re-raise unchanged.
            if cap is not None:
                _end(cap, on_end)

    setattr(tee_with_progress, MARK, True)
    entity.__dict__[PATCHED_ATTR] = tee_with_progress
    return True


def uninstall(entity: Any) -> None:
    """Drop the shadow, so the class method applies again."""
    if is_installed(entity):
        del entity.__dict__[PATCHED_ATTR]
