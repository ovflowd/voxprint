"""One speaker's voiceprint: speaker embeddings, never audio. Plain Python, no Home Assistant imports.

A voiceprint is the list of unit-length embeddings enrolled for a speaker, newest last, capped at
MAX_SAMPLES. An utterance scores as its cosine similarity to the normalized mean of that list.
Embeddings are stored as base64 float16.
"""

from __future__ import annotations

import base64
import math
import struct

MAX_SAMPLES = 150


def _unit(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v)) or 1e-9
    return [x / n for x in v]


def encode(v: list[float]) -> str:
    return base64.b64encode(struct.pack(f"<{len(v)}e", *v)).decode()


def decode(s: str) -> list[float]:
    b = base64.b64decode(s, validate=True)
    return list(struct.unpack(f"<{len(b) // 2}e", b))


class Voiceprint:
    def __init__(self, samples: list[list[float]] | None = None) -> None:
        self.samples = [_unit(v) for v in samples or []][-MAX_SAMPLES:]
        self._centroid: list[float] | None = None

    @property
    def enrolled(self) -> int:
        return len(self.samples)

    def score(self, embedding: list[float]) -> float | None:
        """Cosine similarity to the voiceprint, or None while nothing is enrolled."""
        if not self.samples:
            return None
        if self._centroid is None:
            self._centroid = _unit([sum(col) for col in zip(*self.samples, strict=True)])
        return sum(a * b for a, b in zip(_unit(embedding), self._centroid, strict=True))

    def add(self, embedding: list[float]) -> None:
        self.samples.append(_unit(embedding))
        del self.samples[:-MAX_SAMPLES]
        self._centroid = None

    def clear(self) -> None:
        self.samples.clear()
        self._centroid = None

    def to_json(self) -> list[str]:
        return [encode(v) for v in self.samples]

    @classmethod
    def from_json(cls, data: list[str]) -> Voiceprint:
        return cls([decode(s) for s in data])
