"""Diagnostics hold no names, persons, addresses or embeddings."""

from __future__ import annotations

import json

from aiohttp import ClientError
from homeassistant.core import HomeAssistant
from pytest_homeassistant.common import MockConfigEntry
from pytest_homeassistant.components.diagnostics import get_diagnostics_for_config_entry
from pytest_homeassistant.typing import ClientSessionGenerator

from custom_components.voxprint.const import MODEL
from custom_components.voxprint.voiceprint import encode
from fakes import APP_URL, BEDROOM, KITCHEN, LOOSE, VOICES, FakeApp, FakeSatellite, audio, utter, voiceprint


async def test_diagnostics_number_the_speakers_and_leave_out_anything_personal(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    voxprint: MockConfigEntry,
    satellites: dict[str, FakeSatellite],
) -> None:
    voiceprint(voxprint, "Alice").add(VOICES[1])
    await utter(hass, satellites[KITCHEN], audio(1))
    diagnostics = await get_diagnostics_for_config_entry(hass, hass_client, voxprint)
    text = json.dumps(diagnostics)
    for personal in ("Alice", "Bob", "person.alice", "user-alice", APP_URL, encode(VOICES[1])):
        assert personal not in text
    assert diagnostics["model"] == MODEL
    assert diagnostics["app"]["model"] == MODEL
    assert diagnostics["options"]["satellites"] == [KITCHEN, BEDROOM, LOOSE]
    assert diagnostics["speakers"] == {
        "speaker_1": {"enrolled": 1, "enrolling": False, "has_person": True},
        "speaker_2": {"enrolled": 0, "enrolling": False, "has_person": False},
    }
    assert diagnostics["results"][KITCHEN] == {
        "speaker": "speaker_1",
        "score": 1.0,
        "scores": {"speaker_1": 1.0},
        "speech_s": 2.0,
        "error": None,
    }
    assert diagnostics["tee"] == {"stt.fake_stt": True}


async def test_diagnostics_say_when_the_app_is_down(
    hass: HomeAssistant, hass_client: ClientSessionGenerator, voxprint: MockConfigEntry, fake_app: FakeApp
) -> None:
    fake_app.health = ClientError()
    diagnostics = await get_diagnostics_for_config_entry(hass, hass_client, voxprint)
    assert diagnostics["app"] == {"error": "app_unavailable"}
