"""Who spoke: utterances through the real Assist pipeline, scored against enrolled voiceprints."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from typing import Any

from aiohttp import ClientError
from homeassistant.components.assist_pipeline import PipelineEventType
from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er, issue_registry as ir
import pytest
from pytest_homeassistant.common import MockConfigEntry, async_capture_events

from custom_components.voxprint import tee
from custom_components.voxprint.const import CONF_SATELLITES, DOMAIN, MODEL
from fakes import (
    BEDROOM,
    KITCHEN,
    LOOSE,
    META,
    SPEECH_S,
    STT_TEXT,
    VOICES,
    FakeApp,
    FakeSatellite,
    FakeSTT,
    audio,
    utter,
    voiceprint,
)

KITCHEN_SENSOR = "sensor.kitchen_speaker"


@pytest.fixture
def enrolled(voxprint: MockConfigEntry) -> MockConfigEntry:
    voiceprint(voxprint, "Alice").add(VOICES[1])
    voiceprint(voxprint, "Bob").add(VOICES[2])
    return voxprint


class States:
    """The states an entity goes through, from now on."""

    def __init__(self, hass: HomeAssistant, entity_id: str) -> None:
        self._events = async_capture_events(hass, EVENT_STATE_CHANGED)
        self._entity_id = entity_id

    def __iter__(self) -> Iterator[State]:
        return (e.data["new_state"] for e in self._events if e.data["entity_id"] == self._entity_id)


async def test_each_satellite_gets_a_speaker_sensor_on_its_own_device(
    hass: HomeAssistant, voxprint: MockConfigEntry, entity_registry: er.EntityRegistry
) -> None:
    sensor = entity_registry.async_get(KITCHEN_SENSOR)
    assert sensor.device_id == entity_registry.async_get(KITCHEN).device_id
    state = hass.states.get(KITCHEN_SENSOR)
    assert state.state == "unknown"
    assert state.attributes["options"] == ["Alice", "Bob"]
    assert state.attributes["error"] == "no_utterance"
    assert state.attributes["friendly_name"] == "Kitchen Speaker"
    assert hass.states.get("sensor.bedroom_speaker") is not None


async def test_a_satellite_without_a_device_names_its_sensor_after_itself(
    hass: HomeAssistant, voxprint: MockConfigEntry, entity_registry: er.EntityRegistry
) -> None:
    assert entity_registry.async_get("sensor.loose_speaker").device_id is None
    assert hass.states.get("sensor.loose_speaker").attributes["friendly_name"] == "Loose speaker"


async def test_a_known_voice_names_its_speaker_and_their_person(
    hass: HomeAssistant, enrolled: MockConfigEntry, satellites: dict[str, FakeSatellite]
) -> None:
    await utter(hass, satellites[KITCHEN], audio(3))
    state = hass.states.get(KITCHEN_SENSOR)
    assert state.state == "Alice"
    assert state.attributes["person"] == "person.alice"
    assert state.attributes["user_id"] == "user-alice"
    assert state.attributes["score"] == 0.97
    assert state.attributes["scores"] == {"Alice": 0.97, "Bob": 0.243}
    assert state.attributes["speech_s"] == SPEECH_S
    assert state.attributes["threshold"] == 0.5
    assert state.attributes["error"] is None


async def test_a_speaker_without_a_person_has_no_user_id(
    hass: HomeAssistant, enrolled: MockConfigEntry, satellites: dict[str, FakeSatellite]
) -> None:
    await utter(hass, satellites[KITCHEN], audio(2))
    state = hass.states.get(KITCHEN_SENSOR)
    assert state.state == "Bob"
    assert state.attributes["person"] is None
    assert state.attributes["user_id"] is None


async def test_a_voice_below_the_threshold_names_nobody_but_keeps_its_scores(
    hass: HomeAssistant, enrolled: MockConfigEntry, satellites: dict[str, FakeSatellite]
) -> None:
    await utter(hass, satellites[KITCHEN], audio(5))
    state = hass.states.get(KITCHEN_SENSOR)
    assert state.state == "unknown"
    assert state.attributes["error"] is None
    assert state.attributes["scores"] == {"Alice": 0.0, "Bob": 0.0}


async def test_two_speakers_too_close_to_tell_apart_name_nobody(
    hass: HomeAssistant, enrolled: MockConfigEntry, satellites: dict[str, FakeSatellite]
) -> None:
    await utter(hass, satellites[KITCHEN], audio(4))
    state = hass.states.get(KITCHEN_SENSOR)
    assert state.state == "unknown"
    assert state.attributes["error"] == "ambiguous"
    assert state.attributes["scores"] == {"Alice": 0.707, "Bob": 0.707}


async def test_nobody_enrolled_yet_says_so(
    hass: HomeAssistant, voxprint: MockConfigEntry, satellites: dict[str, FakeSatellite]
) -> None:
    await utter(hass, satellites[KITCHEN], audio(1))
    assert hass.states.get(KITCHEN_SENSOR).attributes["error"] == "not_enrolled"


async def test_the_result_resets_while_listening_and_moves_on_every_utterance(
    hass: HomeAssistant, enrolled: MockConfigEntry, satellites: dict[str, FakeSatellite]
) -> None:
    seen = States(hass, KITCHEN_SENSOR)
    await utter(hass, satellites[KITCHEN], audio(1))
    await utter(hass, satellites[KITCHEN], audio(1))
    states = list(seen)
    assert [(s.state, s.attributes["error"]) for s in states] == [
        ("unknown", "listening"),
        ("Alice", None),
        ("unknown", "listening"),
        ("Alice", None),
    ]
    assert states[1].last_updated < states[3].last_updated


async def test_stt_gets_every_byte_and_its_transcript_is_unchanged(
    hass: HomeAssistant,
    enrolled: MockConfigEntry,
    satellites: dict[str, FakeSatellite],
    stt_engine: FakeSTT,
    fake_app: FakeApp,
) -> None:
    voice = audio(1, seconds=1.5)
    await utter(hass, satellites[KITCHEN], voice)
    assert bytes(stt_engine.received) == voice
    assert fake_app.audio == [voice]
    stt_end = [e for e in satellites[KITCHEN].events if e.type == PipelineEventType.STT_END]
    assert stt_end[0].data["stt_output"]["text"] == STT_TEXT


async def test_audio_from_outside_a_satellite_is_never_captured(
    hass: HomeAssistant, enrolled: MockConfigEntry, stt_engine: FakeSTT, fake_app: FakeApp
) -> None:
    async def browser() -> AsyncIterator[bytes]:
        yield audio(1)

    before = hass.states.get(KITCHEN_SENSOR)
    result = await stt_engine.internal_async_process_audio_stream(META, browser())
    await hass.async_block_till_done(wait_background_tasks=True)
    assert result.text == STT_TEXT
    assert fake_app.audio == []
    assert hass.states.get(KITCHEN_SENSOR) == before


async def test_a_satellite_that_is_not_configured_is_never_captured(
    hass: HomeAssistant,
    assist: None,
    fake_app: FakeApp,
    config_entry: MockConfigEntry,
    satellites: dict[str, FakeSatellite],
) -> None:
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(config_entry, options={**config_entry.options, CONF_SATELLITES: [KITCHEN]})
    set_up = await hass.config_entries.async_setup(config_entry.entry_id)
    assert set_up
    await utter(hass, satellites[BEDROOM], audio(1))
    assert fake_app.audio == []
    assert hass.states.get("sensor.bedroom_speaker") is None


async def test_two_satellites_at_once_each_get_their_own_speaker(
    hass: HomeAssistant, enrolled: MockConfigEntry, satellites: dict[str, FakeSatellite], fake_app: FakeApp
) -> None:
    fake_app.delay = 0.05
    await asyncio.gather(satellites[KITCHEN].utter(audio(1)), satellites[BEDROOM].utter(audio(2)))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(KITCHEN_SENSOR).state == "Alice"
    assert hass.states.get("sensor.bedroom_speaker").state == "Bob"


async def test_a_late_score_for_an_older_utterance_is_dropped(
    hass: HomeAssistant, enrolled: MockConfigEntry, satellites: dict[str, FakeSatellite], fake_app: FakeApp
) -> None:
    seen = States(hass, KITCHEN_SENSOR)
    fake_app.delay = 0.2
    await satellites[KITCHEN].utter(audio(1))
    fake_app.delay = 0.0
    await utter(hass, satellites[KITCHEN], audio(2))
    assert hass.states.get(KITCHEN_SENSOR).state == "Bob"
    assert "Alice" not in [s.state for s in seen]


@pytest.mark.parametrize(
    ("reply", "error"),
    [
        (ClientError(), "app_unavailable"),
        ({"model": MODEL, "too_short": True, "voiced_s": 0.2, "total_s": 1.0}, "too_short"),
        ({"model": MODEL, "embedding": VOICES[1], "voiced_s": 0.4, "total_s": 1.0}, "too_short"),
        ({"model": MODEL, "embedding": VOICES[1]}, "bad_response"),
        ({"model": MODEL, "embedding": "not a vector", "voiced_s": 2.0}, "bad_response"),
        ([1.0, 2.0], "bad_response"),
        ({"model": "another_model", "embedding": VOICES[1], "voiced_s": 2.0}, "model_mismatch"),
    ],
)
async def test_a_failure_names_nobody_and_says_why(
    hass: HomeAssistant,
    enrolled: MockConfigEntry,
    satellites: dict[str, FakeSatellite],
    fake_app: FakeApp,
    reply: dict[str, Any] | list[float] | Exception,
    error: str,
) -> None:
    fake_app.replies = [reply]
    await utter(hass, satellites[KITCHEN], audio(1))
    state = hass.states.get(KITCHEN_SENSOR)
    assert state.state == "unknown"
    assert state.attributes["error"] == error


async def test_an_app_slower_than_the_timeout_names_nobody(
    hass: HomeAssistant,
    enrolled: MockConfigEntry,
    satellites: dict[str, FakeSatellite],
    fake_app: FakeApp,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("custom_components.voxprint.client.REQUEST_TIMEOUT_S", 0.05)
    fake_app.delay = 0.2
    await utter(hass, satellites[KITCHEN], audio(1))
    assert hass.states.get(KITCHEN_SENSOR).attributes["error"] == "app_timeout"


async def test_an_app_with_another_model_raises_a_repair_until_it_answers_right(
    hass: HomeAssistant,
    enrolled: MockConfigEntry,
    satellites: dict[str, FakeSatellite],
    fake_app: FakeApp,
    issue_registry: ir.IssueRegistry,
) -> None:
    fake_app.replies = [{"model": "another_model", "embedding": VOICES[1], "voiced_s": 2.0}]
    await utter(hass, satellites[KITCHEN], audio(1))
    issue = issue_registry.async_get_issue(DOMAIN, "app_incompatible")
    assert issue.translation_placeholders == {"model": "another_model"}
    assert issue.config_entry_id == enrolled.entry_id
    await utter(hass, satellites[KITCHEN], audio(1))
    assert issue_registry.async_get_issue(DOMAIN, "app_incompatible") is None
    assert hass.states.get(KITCHEN_SENSOR).state == "Alice"


async def test_a_satellite_whose_engine_the_tee_cannot_hear_reports_it(
    hass: HomeAssistant,
    assist: None,
    fake_app: FakeApp,
    config_entry: MockConfigEntry,
    satellites: dict[str, FakeSatellite],
    stt_engine: FakeSTT,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tee, "install", lambda *args: False)
    config_entry.add_to_hass(hass)
    set_up = await hass.config_entries.async_setup(config_entry.entry_id)
    assert set_up
    await utter(hass, satellites[KITCHEN], audio(1))
    assert bytes(stt_engine.received) == audio(1)
    assert fake_app.audio == []
    assert hass.states.get(KITCHEN_SENSOR).attributes["error"] == "not_captured"


async def test_the_loose_satellite_is_heard_like_any_other(
    hass: HomeAssistant, enrolled: MockConfigEntry, satellites: dict[str, FakeSatellite]
) -> None:
    await utter(hass, satellites[LOOSE], audio(2))
    assert hass.states.get("sensor.loose_speaker").state == "Bob"


async def test_a_request_that_skips_listening_clears_the_last_verdict(
    hass: HomeAssistant, enrolled: MockConfigEntry, satellites: dict[str, FakeSatellite]
) -> None:
    await utter(hass, satellites[KITCHEN], audio(1))
    before = hass.states.get(KITCHEN_SENSOR)
    assert before.state == "Alice"
    # STT on the satellite itself: the pipeline starts at the intent stage, so it goes straight to processing.
    hass.states.async_set(KITCHEN, "idle")
    hass.states.async_set(KITCHEN, "processing")
    await hass.async_block_till_done()
    after = hass.states.get(KITCHEN_SENSOR)
    assert after.state == "unknown"
    assert after.attributes["error"] == "not_captured"
    assert after.last_updated > before.last_updated


async def test_an_attribute_change_while_processing_leaves_the_result_alone(
    hass: HomeAssistant, enrolled: MockConfigEntry, satellites: dict[str, FakeSatellite]
) -> None:
    hass.states.async_set(KITCHEN, "processing")
    await hass.async_block_till_done()
    before = hass.states.get(KITCHEN_SENSOR)
    hass.states.async_set(KITCHEN, "processing", {"friendly_name": "Kitchen, renamed"})
    await hass.async_block_till_done()
    assert hass.states.get(KITCHEN_SENSOR).last_updated == before.last_updated
