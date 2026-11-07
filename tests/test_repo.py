"""What the stores read from this repository, and what must never be committed to it."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import re
import struct
import subprocess
import tomllib

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "custom_components" / "voxprint"
TRANSLATIONS = json.loads((INTEGRATION / "translations" / "en.json").read_text())


def tracked() -> list[Path]:
    """Files in git, and files git would add: what the stores and a clone get."""
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=ROOT,
            capture_output=True,
            check=True,
        ).stdout
    except OSError, subprocess.CalledProcessError:
        pytest.skip("not a git checkout")
    return [Path(p) for p in out.decode().split("\0") if p]


def png_size(path: Path) -> tuple[int, int]:
    header = path.read_bytes()[:24]
    assert header[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", header[16:24])


def test_the_supervisor_finds_exactly_one_app() -> None:
    # Supervisor's own rule (supervisor/store/data.py): every config.{json,yaml,yml} outside dot and rootfs folders.
    configs = [
        p
        for p in tracked()
        if p.stem == "config"
        and p.suffix in (".json", ".yaml", ".yml")
        and not any(part.startswith(".") or part == "rootfs" for part in p.parts)
    ]
    assert configs == [Path("app/config.yaml")]
    assert (ROOT / "repository.yaml").is_file()


def test_the_versions_agree() -> None:
    manifest = json.loads((INTEGRATION / "manifest.json").read_text())
    app = yaml.safe_load((ROOT / "app" / "config.yaml").read_text())
    assert tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"] == manifest["version"]
    assert tomllib.loads((ROOT / "app" / "pyproject.toml").read_text())["project"]["version"] == app["version"]
    assert json.loads((ROOT / "hacs.json").read_text())["name"] == manifest["name"]


def test_the_app_config_is_complete() -> None:
    config = yaml.safe_load((ROOT / "app" / "config.yaml").read_text())
    translations = yaml.safe_load((ROOT / "app" / "translations" / "en.yaml").read_text())
    assert set(config["arch"]) <= {"aarch64", "amd64"}
    assert config["image"] == "ghcr.io/ovflowd/voxprint"
    assert not config.get("hassio_api", False)
    assert not config.get("homeassistant_api", False)
    assert "ports" not in config
    assert set(config["options"]) == set(config["schema"]) == set(translations["configuration"])
    for name in ("DOCS.md", "README.md", "CHANGELOG.md", "icon.png", "logo.png"):
        assert (ROOT / "app" / name).is_file(), name


def test_the_brand_images_have_the_sizes_home_assistant_expects() -> None:
    assert png_size(INTEGRATION / "brand" / "icon.png") == (256, 256)
    assert png_size(INTEGRATION / "brand" / "icon@2x.png") == (512, 512)
    assert png_size(ROOT / "app" / "icon.png") == (128, 128)


def test_no_voice_recording_voiceprint_or_model_is_committed() -> None:
    forbidden = {".wav", ".flac", ".mp3", ".ogg", ".m4a", ".opus", ".npy", ".npz", ".onnx", ".pt"}
    assert [p for p in tracked() if p.suffix.lower() in forbidden] == []
    assert [p for p in tracked() if ".storage" in p.parts] == []


def test_every_error_the_sensor_can_show_is_translated() -> None:
    sources = "\n".join(p.read_text() for p in INTEGRATION.glob("*.py"))
    errors = {
        *re.findall(r'Result\("(\w+)"', sources),
        *re.findall(r'AppError\("(\w+)"', sources),
        *re.findall(r'result\("(\w+)"', sources),
    }
    errors -= {"app_incompatible"}
    states = TRANSLATIONS["entity"]["sensor"]["speaker"]["state_attributes"]["error"]["state"]
    assert errors == set(states)


def test_every_repair_and_entity_key_is_translated_and_has_an_icon() -> None:
    sources = "\n".join(p.read_text() for p in INTEGRATION.glob("*.py"))
    issues = set(re.findall(r'_create_issue\(\s*"(\w+)"', sources)) | set(
        re.findall(r'delete_issue\([^)]*"(\w+)"\)', sources)
    )
    assert issues == set(TRANSLATIONS["issues"])
    icons = json.loads((INTEGRATION / "icons.json").read_text())["entity"]
    for platform, entities in icons.items():
        assert set(entities) == set(TRANSLATIONS["entity"][platform]), platform


def test_every_await_is_a_statement_of_its_own() -> None:
    # House style: `x = await f()`, then use x; never `g(await f())`, `assert await f()` or `(await f()).x`.
    allowed = (ast.Expr, ast.Assign, ast.AnnAssign, ast.Return)
    nested = []
    for path in tracked():
        if path.suffix != ".py":
            continue
        tree = ast.parse((ROOT / path).read_text())
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                if isinstance(child, ast.Await) and not isinstance(parent, allowed):
                    nested.append(f"{path}:{child.lineno}")
    assert nested == []
