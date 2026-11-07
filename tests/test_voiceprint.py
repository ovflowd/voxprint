"""A voiceprint's maths and storage format. Plain Python."""

from __future__ import annotations

import random

import pytest

from custom_components.voxprint.voiceprint import MAX_SAMPLES, Voiceprint, decode, encode

rng = random.Random(0)


def vec() -> list[float]:
    return [rng.gauss(0, 1) for _ in range(256)]


def test_an_empty_voiceprint_scores_nothing() -> None:
    assert Voiceprint().score(vec()) is None
    assert Voiceprint().enrolled == 0


def test_a_voice_scores_one_against_a_voiceprint_of_itself() -> None:
    v = vec()
    vp = Voiceprint()
    vp.add(v)
    assert vp.score(v) == pytest.approx(1.0)
    assert vp.score([-x for x in v]) == pytest.approx(-1.0)


def test_the_score_is_the_cosine_to_the_mean_of_the_samples() -> None:
    vp = Voiceprint([[1.0, 0.0], [0.0, 1.0]])
    assert vp.score([1.0, 1.0]) == pytest.approx(1.0)
    assert vp.score([1.0, 0.0]) == pytest.approx(0.7071, abs=1e-4)


def test_storage_keeps_float16_embeddings_only() -> None:
    v = vec()
    vp = Voiceprint()
    vp.add(v)
    data = vp.to_json()
    assert isinstance(data, list)
    assert len(data[0]) == 684
    assert Voiceprint.from_json(data).score(v) == pytest.approx(1.0, abs=1e-3)
    assert decode(encode([0.5, -0.25])) == [0.5, -0.25]


def test_only_the_newest_samples_are_kept() -> None:
    vectors = [vec() for _ in range(MAX_SAMPLES + 20)]
    vp = Voiceprint()
    for v in vectors:
        vp.add(v)
    assert vp.enrolled == MAX_SAMPLES
    assert vp.samples == Voiceprint(vectors[20:]).samples
    assert Voiceprint(vectors).samples == vp.samples


def test_clear_empties_it() -> None:
    vp = Voiceprint([vec()])
    vp.clear()
    assert vp.score(vec()) is None


def test_corrupt_storage_is_refused() -> None:
    with pytest.raises(ValueError):
        decode("not base64!")
