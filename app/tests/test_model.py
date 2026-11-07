"""The real WeSpeaker model on synthetic voices. Skipped when the model file isn't there."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

import server
from synth import HIGH, LOW, pcm, voice, with_silence

REFERENCE = Path(__file__).with_name("reference_embedding.json")


@pytest.fixture(scope="module")
def service(model: server.Model) -> server.Service:
    return server.Service(model)


def embedding(service: server.Service, x: np.ndarray) -> np.ndarray:
    return np.array(service.compute(pcm(with_silence(x)))["embedding"])


def test_the_self_test_returns_a_unit_vector(service: server.Service) -> None:
    assert service.self_test() == 1.0


def test_the_embedding_matches_the_recorded_reference(service: server.Service) -> None:
    # Catches a dependency update (onnxruntime, kaldi-native-fbank, numpy) that moves the numbers, which
    # would quietly shift every enrolled voiceprint's scores.
    reference = np.array(json.loads(REFERENCE.read_text()))
    assert float(embedding(service, voice(*LOW, seed=1)) @ reference) > 0.999


def test_the_same_voice_scores_higher_than_another_voice(service: server.Service) -> None:
    first = embedding(service, voice(*LOW, seed=1))
    again = embedding(service, voice(*LOW, seed=2))
    other = embedding(service, voice(*HIGH, seed=1))
    assert float(first @ again) > 0.9
    assert float(first @ other) < 0.7


def test_loudness_barely_moves_the_embedding(service: server.Service) -> None:
    loud = embedding(service, voice(*LOW, seed=1, level=0.5))
    for level in (0.01, 0.05):
        assert float(loud @ embedding(service, voice(*LOW, seed=1, level=level))) > 0.99
