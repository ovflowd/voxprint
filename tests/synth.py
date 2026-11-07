"""Synthetic speech-like audio in plain Python: a voice is a pitch and a set of formants, never a recording."""

from __future__ import annotations

import math
import random
import struct

SR = 16000

LOW = (120.0, (500.0, 1500.0, 2500.0))
HIGH = (220.0, (850.0, 1200.0, 2800.0))
MIDDLE = (165.0, (650.0, 1750.0, 2350.0))


def voice(f0: float, formants: tuple[float, ...], seconds: float = 2.0, seed: int = 0) -> bytes:
    """s16le PCM: harmonics of f0 shaped by formant peaks, with vibrato and syllables, between silences."""
    rng = random.Random(seed)
    vibrato, syllables = rng.uniform(0, 2 * math.pi), rng.uniform(0, 2 * math.pi)
    gains = [
        (k, sum(math.exp(-((((k * f0) - f) / 120.0) ** 2)) for f in formants) / math.sqrt(k))
        for k in range(1, int(4000 / f0))
    ]
    gains = [(k, g) for k, g in gains if g > 1e-3]
    samples, phase = [], 0.0
    for n in range(int(seconds * SR)):
        t = n / SR
        phase += 2 * math.pi * f0 * (1 + 0.03 * math.sin(2 * math.pi * 5 * t + vibrato)) / SR
        envelope = 0.6 + 0.4 * math.sin(2 * math.pi * 4 * t + syllables)
        samples.append(envelope * sum(g * math.sin(k * phase) for k, g in gains) + 0.003 * rng.gauss(0, 1))
    peak = max(abs(x) for x in samples)
    pad = [0.0] * (SR // 2)
    return pcm([*pad, *(0.1 * x / peak for x in samples), *pad])


def silence(seconds: float = 1.0) -> bytes:
    return bytes(int(seconds * SR) * 2)


def pcm(samples: list[float]) -> bytes:
    return struct.pack(f"<{len(samples)}h", *(round(max(-1.0, min(1.0, x)) * 32767) for x in samples))
