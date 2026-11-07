"""End to end: the integration, the real app server and model, and synthetic voices through the real pipeline.

Skipped unless the app's environment and the model are there:

    (cd app && uv sync) && python3 -I app/fetch_model.py models
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
import os
from pathlib import Path
import socket
import subprocess

from aiohttp import ClientError, ClientSession
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest

from custom_components.voxprint.const import CONF_PERSON, CONF_SATELLITES, CONF_URL, DOMAIN
from fakes import KITCHEN, STT_TEXT, FakeSatellite, FakeSTT, utter
from synth import HIGH, LOW, MIDDLE, silence, voice

ROOT = Path(__file__).resolve().parents[1]
APP_PYTHON = ROOT / "app" / ".venv" / "bin" / "python"
MODEL_DIR = Path(os.environ.get("VOXPRINT_MODEL_DIR", ROOT / "models"))
SENSOR = "sensor.kitchen_speaker"


@pytest.fixture
async def app_url(socket_enabled: None) -> AsyncIterator[str]:
    if not APP_PYTHON.exists() or not (MODEL_DIR / "wespeaker_en_voxceleb_resnet34_LM.onnx").exists():
        pytest.skip("needs app/.venv and the model: (cd app && uv sync) && python3 -I app/fetch_model.py models")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {**os.environ, "HOST": "127.0.0.1", "PORT": str(port), "MODEL_DIR": str(MODEL_DIR)}
    server = subprocess.Popen([APP_PYTHON, "-I", ROOT / "app" / "server.py"], env=env)
    url = f"http://127.0.0.1:{port}"
    try:
        async with ClientSession() as session:
            for _ in range(150):
                try:
                    async with session.get(f"{url}/health") as resp:
                        if resp.status == 200:
                            break
                except ClientError:
                    pass
                if server.poll() is not None:
                    pytest.fail(f"the app exited with {server.returncode}")
                await asyncio.sleep(0.1)
        yield url
    finally:
        server.terminate()
        server.wait(timeout=10)


async def flow(hass: HomeAssistant, url: str) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: url, CONF_SATELLITES: [KITCHEN]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY, result.get("errors")
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    for speaker in ({CONF_NAME: "Alice", CONF_PERSON: "person.alice"}, {CONF_NAME: "Bob"}):
        result = await hass.config_entries.subentries.async_init(
            (entry.entry_id, "speaker"), context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.subentries.async_configure(result["flow_id"], speaker)
        assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()


async def enroll(hass: HomeAssistant, satellite: FakeSatellite, switch: str, who: tuple) -> None:
    await hass.services.async_call("switch", "turn_on", {"entity_id": switch}, blocking=True)
    for seed in range(1, 5):
        await utter(hass, satellite, voice(*who, seed=seed))
    await hass.services.async_call("switch", "turn_off", {"entity_id": switch}, blocking=True)


async def test_two_enrolled_voices_are_told_apart_through_the_real_app(
    hass: HomeAssistant,
    assist: None,
    app_url: str,
    satellites: dict[str, FakeSatellite],
    stt_engine: FakeSTT,
) -> None:
    await flow(hass, app_url)
    kitchen = satellites[KITCHEN]

    await utter(hass, kitchen, voice(*LOW, seed=1))
    assert hass.states.get(SENSOR).attributes["error"] == "not_enrolled"

    await enroll(hass, kitchen, "switch.alice_enrollment", LOW)
    await enroll(hass, kitchen, "switch.bob_enrollment", HIGH)
    assert hass.states.get("sensor.alice_enrolled_utterances").state == "4"
    assert hass.states.get("sensor.bob_enrolled_utterances").state == "4"

    await utter(hass, kitchen, voice(*LOW, seed=9))
    alice = hass.states.get(SENSOR)
    assert alice.state == "Alice", alice.attributes
    assert alice.attributes["user_id"] == "user-alice"
    assert 1.8 < alice.attributes["speech_s"] < 2.3
    assert stt_engine.received == bytearray(voice(*LOW, seed=9))
    stt_end = [e for e in kitchen.events if e.type == "stt-end"]
    assert stt_end[-1].data["stt_output"]["text"] == STT_TEXT

    await utter(hass, kitchen, voice(*HIGH, seed=9))
    bob = hass.states.get(SENSOR)
    assert bob.state == "Bob", bob.attributes
    assert bob.attributes["scores"]["Bob"] > bob.attributes["scores"]["Alice"] + 0.3

    await utter(hass, kitchen, voice(*MIDDLE, seed=9))
    other = hass.states.get(SENSOR).attributes
    assert other["error"] in (None, "ambiguous")
    assert max(other["scores"].values()) < max(alice.attributes["scores"].values())

    await utter(hass, kitchen, silence())
    assert hass.states.get(SENSOR).attributes["error"] == "too_short"
