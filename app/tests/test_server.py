"""The service around the model: the speech gate, the HTTP API and the options, with a fake model."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from pathlib import Path
import re
import threading
import time

from aiohttp import ClientTimeout
import numpy as np

from conftest import FakeModel
import server
from synth import LOW, SR, pcm, voice, with_silence

APP = Path(__file__).resolve().parents[1]


def dbfs(x: np.ndarray) -> float:
    return 20 * np.log10(float(np.percentile(np.abs(x), 99.9)))


def test_normalized_lifts_quiet_speech_to_about_minus_20_dbfs() -> None:
    quiet = voice(*LOW, level=0.001)
    assert dbfs(quiet) < -55
    assert abs(dbfs(server.normalized(quiet)) - -20) < 0.5


def test_normalized_leaves_digital_silence_alone() -> None:
    silence = np.zeros(SR, np.float32)
    assert server.normalized(silence) is silence
    assert len(server.normalized(np.zeros(0, np.float32))) == 0


def test_voiced_keeps_speech_and_drops_the_silence_around_it() -> None:
    x = server.normalized(with_silence(voice(*LOW, seconds=2.0), pad_s=1.0))
    kept = len(server.voiced(x)) / SR
    assert 1.8 < kept < 2.3


def test_voiced_is_empty_for_less_than_one_frame() -> None:
    assert len(server.voiced(np.ones(server.FRAME - 1, np.float32))) == 0


def test_compute_says_too_short_for_silence_and_never_runs_the_model(
    fake_service: server.Service, fake_model: FakeModel
) -> None:
    result = fake_service.compute(bytes(2 * SR))
    assert result == {"too_short": True, "model": server.MODEL_ID, "total_s": 1.0, "voiced_s": 0.0}
    assert fake_model.inputs == []


def test_compute_embeds_at_most_six_seconds_of_speech(fake_service: server.Service, fake_model: FakeModel) -> None:
    result = fake_service.compute(pcm(with_silence(voice(*LOW, seconds=9.0), pad_s=1.5)))
    assert result["embedding"][0] == 1.0
    assert len(result["embedding"]) == 256
    assert result["total_s"] == 12.0
    assert result["voiced_s"] == server.MAX_VOICED_S
    assert len(fake_model.inputs[0]) == server.MAX_VOICED_S * SR


async def test_health_reports_the_api_model_and_version(aiohttp_client, fake_service: server.Service) -> None:
    client = await aiohttp_client(server.make_app(fake_service))
    resp = await client.get("/health")
    assert resp.status == 200
    body = await resp.json()
    assert body == {"ok": True, "api": 1, "model": server.MODEL_ID, "version": server.__version__}


async def test_embed_answers_with_the_embedding(aiohttp_client, fake_service: server.Service) -> None:
    client = await aiohttp_client(server.make_app(fake_service))
    resp = await client.post("/v1/embed", data=pcm(with_silence(voice(*LOW))))
    body = await resp.json()
    assert resp.status == 200
    assert body["model"] == server.MODEL_ID
    assert len(body["embedding"]) == 256
    assert 2.8 < body["voiced_s"] < 3.3


async def test_embed_refuses_an_odd_byte_count_and_more_than_15_seconds(
    aiohttp_client, fake_service: server.Service
) -> None:
    client = await aiohttp_client(server.make_app(fake_service))
    odd = await client.post("/v1/embed", data=b"\x00" * 3)
    long = await client.post("/v1/embed", data=bytes(server.MAX_BODY + 2))
    assert odd.status == 400
    assert long.status in (400, 413)


async def test_more_requests_than_it_queues_are_refused(aiohttp_client) -> None:
    class SlowModel(FakeModel):
        def embed(self, x: np.ndarray) -> np.ndarray:
            time.sleep(0.1)
            return super().embed(x)

    client = await aiohttp_client(server.make_app(server.Service(SlowModel())))
    body = pcm(with_silence(voice(*LOW, seconds=1.0)))
    responses = await asyncio.gather(*(client.post("/v1/embed", data=body) for _ in range(server.MAX_REQUESTS + 3)))
    statuses = sorted(resp.status for resp in responses)
    assert statuses == [200] * server.MAX_REQUESTS + [503] * 3


async def test_requests_never_compute_side_by_side_even_when_clients_give_up(aiohttp_server, aiohttp_client) -> None:
    class CountingModel(FakeModel):
        def __init__(self) -> None:
            super().__init__()
            self.running = self.most = 0
            self.guard = threading.Lock()

        def embed(self, x: np.ndarray) -> np.ndarray:
            with self.guard:
                self.running += 1
                self.most = max(self.most, self.running)
            time.sleep(0.1)
            with self.guard:
                self.running -= 1
            return super().embed(x)

    model = CountingModel()
    service = server.Service(model)
    # The test server cancels the handler of a client that went away, which the app itself doesn't.
    app = await aiohttp_server(server.make_app(service))
    client = await aiohttp_client(app)
    body = pcm(with_silence(voice(*LOW, seconds=1.0)))
    for _ in range(4):
        with contextlib.suppress(TimeoutError):
            await client.post("/v1/embed", data=body, timeout=ClientTimeout(total=0.02))
    responses = await asyncio.gather(*(client.post("/v1/embed", data=body) for _ in range(3)))
    assert [resp.status for resp in responses] == [200] * 3
    assert model.most == 1
    assert service.requests == 0


def test_log_level_reads_the_app_option(tmp_path: Path) -> None:
    options = tmp_path / "options.json"
    options.write_text(json.dumps({"log_level": "debug"}))
    assert server.log_level(options) == logging.DEBUG
    options.write_text(json.dumps({"log_level": "nonsense"}))
    assert server.log_level(options) == logging.INFO
    options.write_text("not json")
    assert server.log_level(options) == logging.INFO
    assert server.log_level(tmp_path / "missing.json") == logging.INFO


def test_the_version_matches_the_app_config_and_changelog() -> None:
    config = (APP / "config.yaml").read_text()
    assert re.search(rf'^version: "{re.escape(server.__version__)}"$', config, re.MULTILINE)
    assert f"## {server.__version__}\n" in (APP / "CHANGELOG.md").read_text()
