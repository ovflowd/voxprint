"""Voxprint app: a stateless speaker-embedding service (WeSpeaker ResNet34-LM).

POST /v1/embed  body = raw PCM s16le, 16 kHz, mono, at most 15 s
  -> 200 {"model", "embedding": [256 floats], "voiced_s", "total_s", "ms"}
  -> 200 {"model", "too_short": true, "voiced_s", "total_s"} when there is too little speech to embed
GET  /health    -> 200 {"ok": true, "api", "model", "version"}

Audio lives in RAM for one request and is never written anywhere. The service keeps no state.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import logging
import os
from pathlib import Path
import time

from aiohttp import web
import kaldi_native_fbank as knf
import numpy as np
import onnxruntime as ort

__version__ = "0.1.0"

API_VERSION = 1
MODEL_ID = "wespeaker_resnet34_lm"
MODEL_FILE = "wespeaker_en_voxceleb_resnet34_LM.onnx"

SR = 16000
# The Assist pipeline caps an utterance at 15 s.
MAX_BODY = 15 * SR * 2
# Below this there are too few frames for a speaker embedding.
MIN_EMBED_S = 0.3
# Longer speech adds latency, not accuracy.
MAX_VOICED_S = 6.0
# Requests in the app at once, the one being embedded included, until their embedding is done. More are
# refused, so a flood can't pile up audio in RAM.
MAX_REQUESTS = 5
FRAME, HOP = 400, 160
OPTIONS_FILE = Path("/data/options.json")

_LOGGER = logging.getLogger("voxprint")


class Model:
    def __init__(self, path: Path) -> None:
        so = ort.SessionOptions()
        # Two threads halve the latency; with one utterance at a time that is at most two cores.
        so.intra_op_num_threads = 2
        so.inter_op_num_threads = 1
        # Hand activation memory back after each run instead of keeping an arena.
        so.enable_cpu_mem_arena = False
        self.sess = ort.InferenceSession(str(path), so, providers=["CPUExecutionProvider"])
        self.input = self.sess.get_inputs()[0].name

    def embed(self, x: np.ndarray) -> np.ndarray:
        opts = knf.FbankOptions()
        opts.frame_opts.dither = 0.0
        opts.frame_opts.samp_freq = SR
        opts.mel_opts.num_bins = 80
        fb = knf.OnlineFbank(opts)
        # WeSpeaker was trained on int16-range samples.
        fb.accept_waveform(SR, (x * 32768.0).tolist())
        fb.input_finished()
        feats = np.stack([fb.get_frame(i) for i in range(fb.num_frames_ready)]).astype(np.float32)
        # Per-utterance mean normalization; scores collapse without it.
        feats -= feats.mean(axis=0, keepdims=True)
        v = self.sess.run(None, {self.input: feats[None]})[0][0]
        return (v / np.linalg.norm(v)).astype(np.float32)


def normalized(x: np.ndarray) -> np.ndarray:
    """Scale the clip so its loudest samples sit near -20 dBFS.

    Some satellites deliver speech around -60 dBFS (the Home Assistant Voice PE does), which is below
    the speech gate in voiced(). The embedding itself doesn't depend on gain: fbank means are removed
    per utterance.
    """
    ref = float(np.percentile(np.abs(x), 99.9)) if len(x) else 0.0
    if ref < 1e-5:
        # Digital silence: left for voiced() to reject.
        return x
    return np.clip(x * (0.1 / ref), -1.0, 1.0)


def voiced(x: np.ndarray) -> np.ndarray:
    """Keep the 25 ms frames that are more than 10 dB above the clip's noise floor."""
    if len(x) < FRAME:
        return x[:0]
    n = 1 + (len(x) - FRAME) // HOP
    idx = HOP * np.arange(n)[:, None] + np.arange(FRAME)[None, :]
    db = 10 * np.log10(np.mean(x[idx] ** 2, axis=1) + 1e-10)
    floor = float(np.percentile(db, 10))
    starts = HOP * np.flatnonzero((db > floor + 10.0) & (db > -50.0))
    edges = np.zeros(len(x) + 1, dtype=np.int32)
    np.add.at(edges, starts, 1)
    np.add.at(edges, starts + FRAME, -1)
    return x[np.cumsum(edges[:-1]) > 0]


class Service:
    def __init__(self, model: Model) -> None:
        self.model = model
        # One worker: one utterance at a time keeps CPU and RAM bounded.
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="embed")
        self.requests = 0

    def compute(self, pcm: bytes) -> dict:
        x = normalized(np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0)
        y = voiced(x)[: int(MAX_VOICED_S * SR)]
        out = {"model": MODEL_ID, "total_s": round(len(x) / SR, 2), "voiced_s": round(len(y) / SR, 2)}
        if len(y) < MIN_EMBED_S * SR:
            return {"too_short": True, **out}
        t0 = time.perf_counter()
        emb = self.model.embed(y).tolist()
        return {"embedding": emb, **out, "ms": round((time.perf_counter() - t0) * 1000, 1)}

    def self_test(self) -> float:
        """Check on a synthetic tone that the model loads and returns a unit vector."""
        t = np.arange(2 * SR) / SR
        x = 0.1 * np.sin(2 * np.pi * 180 * t) * (1 + 0.5 * np.sin(2 * np.pi * 3 * t))
        x = (x + 0.01 * np.random.default_rng(0).standard_normal(len(x))).astype(np.float32)
        return round(float(np.linalg.norm(self.model.embed(x))), 3)

    async def handle_embed(self, request: web.Request) -> web.Response:
        if self.requests >= MAX_REQUESTS:
            raise web.HTTPServiceUnavailable(text="busy")
        self.requests += 1
        try:
            pcm = await request.read()
            if len(pcm) % 2 or len(pcm) > MAX_BODY:
                raise web.HTTPBadRequest(text="expected s16le mono 16 kHz, at most 15 s")
        except BaseException:
            self.requests -= 1
            raise
        job = asyncio.get_running_loop().run_in_executor(self.executor, self.compute, pcm)
        job.add_done_callback(self._finished)
        # A request the client gave up on still holds its place until its embedding is done, so the next one
        # can't start a second computation beside it.
        result = await asyncio.shield(job)
        _LOGGER.debug(
            "%.2f s audio, %.2f s speech, %s ms", result["total_s"], result["voiced_s"], result.get("ms", "-")
        )
        return web.json_response(result)

    def _finished(self, _job: asyncio.Future[dict]) -> None:
        self.requests -= 1

    async def handle_health(self, _request: web.Request) -> web.Response:
        return web.json_response({"ok": True, "api": API_VERSION, "model": MODEL_ID, "version": __version__})


def make_app(service: Service) -> web.Application:
    app = web.Application(client_max_size=MAX_BODY + 1024)
    app.router.add_post("/v1/embed", service.handle_embed)
    app.router.add_get("/health", service.handle_health)
    return app


def log_level(options_file: Path = OPTIONS_FILE) -> int:
    """The app option `log_level`; INFO outside Home Assistant or when it can't be read."""
    try:
        level = json.loads(options_file.read_text())["log_level"]
    except OSError, ValueError, KeyError, TypeError:
        return logging.INFO
    return logging.getLevelNamesMapping().get(str(level).upper(), logging.INFO)


def main() -> None:
    logging.basicConfig(level=log_level(), format="%(asctime)s %(levelname)s %(message)s")
    # The wheel ships a telemetry client; the image also sets ORT_DISABLE_TELEMETRY=1.
    ort.disable_telemetry_events()
    service = Service(Model(Path(os.environ.get("MODEL_DIR", "/models")) / MODEL_FILE))
    _LOGGER.info("Voxprint app %s, model %s, self-test norm %s", __version__, MODEL_ID, service.self_test())
    web.run_app(
        make_app(service),
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "10340")),
        access_log=None,
        print=None,
        # Stop handling a request the integration gave up on.
        handler_cancellation=True,
    )


if __name__ == "__main__":
    main()
