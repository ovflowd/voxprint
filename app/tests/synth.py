"""Synthetic speech-like audio: a voice is a pitch and a set of formants, never a recording."""

from __future__ import annotations

import numpy as np

SR = 16000


def voice(
    f0: float, formants: tuple[float, ...], seconds: float = 3.0, seed: int = 0, level: float = 0.1
) -> np.ndarray:
    """Harmonics of f0 shaped by formant peaks, with vibrato and a 4 Hz syllable envelope."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * SR)) / SR
    pitch = f0 * (1 + 0.03 * np.sin(2 * np.pi * 5 * t + rng.uniform(0, 2 * np.pi)))
    phase = 2 * np.pi * np.cumsum(pitch) / SR
    x = np.zeros_like(t)
    for k in range(1, int(4000 / f0)):
        gain = sum(np.exp(-((((k * f0) - f) / 120.0) ** 2)) for f in formants) / np.sqrt(k)
        x += gain * np.sin(k * phase)
    x *= 0.6 + 0.4 * np.sin(2 * np.pi * 4 * t + rng.uniform(0, 2 * np.pi))
    x += 0.003 * rng.standard_normal(len(t))
    return (level * x / np.max(np.abs(x))).astype(np.float32)


def with_silence(x: np.ndarray, pad_s: float = 0.5) -> np.ndarray:
    pad = np.zeros(int(pad_s * SR), np.float32)
    return np.concatenate([pad, x, pad])


def pcm(x: np.ndarray) -> bytes:
    return (np.clip(x, -1, 1) * 32767).astype("<i2").tobytes()


LOW = (120.0, (500.0, 1500.0, 2500.0))
HIGH = (220.0, (850.0, 1200.0, 2800.0))
