from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

import server

MODEL_DIR = Path(os.environ.get("VOXPRINT_MODEL_DIR", Path(__file__).resolve().parents[2] / "models"))


class FakeModel:
    """Stands in for the ONNX model: a fixed unit vector, and a record of what it was given."""

    def __init__(self) -> None:
        self.inputs: list[np.ndarray] = []

    def embed(self, x: np.ndarray) -> np.ndarray:
        self.inputs.append(x)
        v = np.zeros(256, np.float32)
        v[0] = 1.0
        return v


@pytest.fixture
def fake_model() -> FakeModel:
    return FakeModel()


@pytest.fixture
def fake_service(fake_model: FakeModel) -> server.Service:
    return server.Service(fake_model)


@pytest.fixture(scope="session")
def model() -> server.Model:
    path = MODEL_DIR / server.MODEL_FILE
    if not path.is_file():
        pytest.skip(f"no model at {path}; run: python3 -I fetch_model.py {MODEL_DIR}")
    return server.Model(path)
