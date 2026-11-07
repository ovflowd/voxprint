"""Enrollment, the stored voiceprints, and deleting them."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed

from custom_components.voxprint import recognizer
from custom_components.voxprint.const import DOMAIN, ENROLL_MINUTES, MODEL, STORAGE_KEY
from custom_components.voxprint.voiceprint import decode, encode
from fakes import BEDROOM, KITCHEN, VOICES, FakeApp, FakeSatellite, audio, subentry_id, utter, voiceprint

ALICE_SWITCH = "switch.alice_enrollment"
BOB_SWITCH = "switch.bob_enrollment"
ALICE_COUNT = "sensor.alice_enrolled_utterances"


async def switch(hass: HomeAssistant, entity_id: str, on: bool) -> None:
    await hass.services.async_call("switch", "turn_on" if on else "turn_off", {"entity_id": entity_id}, blocking=True)


def stored(hass_storage: dict[str, Any]) -> dict[str, Any]:
    return hass_storage[STORAGE_KEY]["data"]


async def test_enrollment_adds_each_utterance_and_stores_only_embeddings(
    hass: HomeAssistant,
    voxprint: MockConfigEntry,
    satellites: dict[str, FakeSatellite],
    hass_storage: dict[str, Any],
) -> None:
    assert hass.states.get(ALICE_SWITCH).state == "off"
    await switch(hass, ALICE_SWITCH, True)
    for _ in range(3):
        await utter(hass, satellites[KITCHEN], audio(1))
    assert hass.states.get(ALICE_COUNT).state == "3"
    data = stored(hass_storage)
    alice, bob = subentry_id(voxprint, "Alice"), subentry_id(voxprint, "Bob")
    assert data == {"model": MODEL, "speakers": {alice: [encode(VOICES[1])] * 3, bob: []}}
    assert decode(data["speakers"][alice][0]) == pytest.approx(VOICES[1], abs=1e-3)


async def test_the_voiceprint_file_is_private(hass: HomeAssistant) -> None:
    with patch.object(recognizer, "Store") as store:
        recognizer.voiceprint_store(hass)
    assert store.call_args.kwargs["private"] is True


async def test_the_first_utterance_enrolls_when_nobody_is_enrolled_yet(
    hass: HomeAssistant, voxprint: MockConfigEntry, satellites: dict[str, FakeSatellite]
) -> None:
    await switch(hass, ALICE_SWITCH, True)
    await utter(hass, satellites[KITCHEN], audio(5))
    assert voiceprint(voxprint, "Alice").enrolled == 1


async def test_only_one_speaker_enrolls_at_a_time(hass: HomeAssistant, voxprint: MockConfigEntry) -> None:
    await switch(hass, ALICE_SWITCH, True)
    await switch(hass, BOB_SWITCH, True)
    assert hass.states.get(ALICE_SWITCH).state == "off"
    assert hass.states.get(BOB_SWITCH).state == "on"
    await switch(hass, ALICE_SWITCH, False)
    assert hass.states.get(BOB_SWITCH).state == "on"
    await switch(hass, BOB_SWITCH, False)
    assert hass.states.get(BOB_SWITCH).state == "off"


async def test_enrollment_skips_audio_unlike_the_voiceprint_so_far(
    hass: HomeAssistant, voxprint: MockConfigEntry, satellites: dict[str, FakeSatellite]
) -> None:
    await switch(hass, ALICE_SWITCH, True)
    await utter(hass, satellites[KITCHEN], audio(1))
    await utter(hass, satellites[KITCHEN], audio(6))
    assert voiceprint(voxprint, "Alice").enrolled == 1


async def test_enrollment_skips_an_utterance_that_matches_another_speaker_better(
    hass: HomeAssistant, voxprint: MockConfigEntry, satellites: dict[str, FakeSatellite]
) -> None:
    voiceprint(voxprint, "Alice").add(VOICES[1])
    voiceprint(voxprint, "Bob").add(VOICES[2])
    await switch(hass, ALICE_SWITCH, True)
    await utter(hass, satellites[KITCHEN], audio(7))
    assert voiceprint(voxprint, "Alice").enrolled == 1
    await utter(hass, satellites[KITCHEN], audio(3))
    assert voiceprint(voxprint, "Alice").enrolled == 2


async def test_someone_who_sounds_like_an_enrolled_speaker_can_still_enroll(
    hass: HomeAssistant, voxprint: MockConfigEntry, satellites: dict[str, FakeSatellite]
) -> None:
    voiceprint(voxprint, "Bob").add(VOICES[2])
    await switch(hass, ALICE_SWITCH, True)
    await utter(hass, satellites[KITCHEN], audio(7))
    assert voiceprint(voxprint, "Alice").enrolled == 1


async def test_enrollment_ignores_utterances_it_cannot_score(
    hass: HomeAssistant, voxprint: MockConfigEntry, satellites: dict[str, FakeSatellite], fake_app: FakeApp
) -> None:
    await switch(hass, ALICE_SWITCH, True)
    fake_app.replies = [{"model": MODEL, "too_short": True, "voiced_s": 0.1, "total_s": 1.0}]
    await utter(hass, satellites[KITCHEN], audio(1))
    assert voiceprint(voxprint, "Alice").enrolled == 0


async def test_enrollment_turns_itself_off(hass: HomeAssistant, voxprint: MockConfigEntry) -> None:
    await switch(hass, ALICE_SWITCH, True)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=ENROLL_MINUTES - 1))
    await hass.async_block_till_done()
    assert hass.states.get(ALICE_SWITCH).state == "on"
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=ENROLL_MINUTES + 1))
    await hass.async_block_till_done()
    assert hass.states.get(ALICE_SWITCH).state == "off"


async def test_enrollment_is_off_after_a_reload_and_the_voiceprint_stays(
    hass: HomeAssistant, voxprint: MockConfigEntry, satellites: dict[str, FakeSatellite]
) -> None:
    await switch(hass, ALICE_SWITCH, True)
    await utter(hass, satellites[KITCHEN], audio(1))
    reloaded = await hass.config_entries.async_reload(voxprint.entry_id)
    assert reloaded
    await hass.async_block_till_done()
    assert hass.states.get(ALICE_SWITCH).state == "off"
    assert hass.states.get(ALICE_COUNT).state == "1"
    await utter(hass, satellites[KITCHEN], audio(1))
    assert hass.states.get("sensor.kitchen_speaker").state == "Alice"


async def test_reset_clears_one_voiceprint(
    hass: HomeAssistant, voxprint: MockConfigEntry, hass_storage: dict[str, Any]
) -> None:
    voiceprint(voxprint, "Alice").add(VOICES[1])
    voiceprint(voxprint, "Bob").add(VOICES[2])
    await hass.services.async_call("button", "press", {"entity_id": "button.alice_reset_voiceprint"}, blocking=True)
    assert hass.states.get(ALICE_COUNT).state == "0"
    speakers = stored(hass_storage)["speakers"]
    assert speakers[subentry_id(voxprint, "Alice")] == []
    assert len(speakers[subentry_id(voxprint, "Bob")]) == 1


async def test_removing_a_speaker_deletes_their_voiceprint(
    hass: HomeAssistant,
    assist: None,
    fake_app: FakeApp,
    config_entry: MockConfigEntry,
    hass_storage: dict[str, Any],
) -> None:
    alice, bob = subentry_id(config_entry, "Alice"), subentry_id(config_entry, "Bob")
    hass_storage[STORAGE_KEY] = {
        "version": 1,
        "key": STORAGE_KEY,
        "data": {"model": MODEL, "speakers": {alice: [encode(VOICES[1])], bob: [encode(VOICES[2])]}},
    }
    config_entry.add_to_hass(hass)
    set_up = await hass.config_entries.async_setup(config_entry.entry_id)
    assert set_up
    assert hass.config_entries.async_remove_subentry(config_entry, bob)
    await hass.async_block_till_done()
    assert stored(hass_storage)["speakers"] == {alice: [encode(VOICES[1])]}
    assert hass.states.get(BOB_SWITCH) is None


async def test_removing_the_integration_deletes_every_voiceprint_even_mid_enrollment(
    hass: HomeAssistant,
    voxprint: MockConfigEntry,
    satellites: dict[str, FakeSatellite],
    fake_app: FakeApp,
    hass_storage: dict[str, Any],
) -> None:
    await switch(hass, ALICE_SWITCH, True)
    await utter(hass, satellites[KITCHEN], audio(1))
    assert STORAGE_KEY in hass_storage
    fake_app.delay = 0.2
    await satellites[KITCHEN].utter(audio(1))
    removed = await hass.config_entries.async_remove(voxprint.entry_id)
    assert removed
    await hass.async_block_till_done(wait_background_tasks=True)
    assert STORAGE_KEY not in hass_storage


async def test_voiceprints_from_another_model_are_cleared_with_a_repair(
    hass: HomeAssistant,
    assist: None,
    fake_app: FakeApp,
    config_entry: MockConfigEntry,
    hass_storage: dict[str, Any],
    issue_registry: ir.IssueRegistry,
) -> None:
    alice = subentry_id(config_entry, "Alice")
    hass_storage[STORAGE_KEY] = {
        "version": 1,
        "key": STORAGE_KEY,
        "data": {"model": "older_model", "speakers": {alice: [encode(VOICES[1])]}},
    }
    config_entry.add_to_hass(hass)
    set_up = await hass.config_entries.async_setup(config_entry.entry_id)
    assert set_up
    assert voiceprint(config_entry, "Alice").enrolled == 0
    assert stored(hass_storage)["model"] == MODEL
    issue = issue_registry.async_get_issue(DOMAIN, "voiceprints_cleared")
    assert issue.translation_placeholders == {"model": "older_model"}


async def test_an_utterance_spoken_before_enrollment_started_is_not_enrolled(
    hass: HomeAssistant, voxprint: MockConfigEntry, satellites: dict[str, FakeSatellite], fake_app: FakeApp
) -> None:
    fake_app.delay = 0.2
    await satellites[KITCHEN].utter(audio(1))
    await switch(hass, BOB_SWITCH, True)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert voiceprint(voxprint, "Bob").enrolled == 0


async def test_an_utterance_whose_enrollment_ended_while_scoring_is_not_enrolled(
    hass: HomeAssistant, voxprint: MockConfigEntry, satellites: dict[str, FakeSatellite], fake_app: FakeApp
) -> None:
    await switch(hass, ALICE_SWITCH, True)
    fake_app.delay = 0.2
    await satellites[KITCHEN].utter(audio(1))
    await switch(hass, ALICE_SWITCH, False)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert voiceprint(voxprint, "Alice").enrolled == 0


async def test_enrollment_listens_to_the_first_satellite_that_hears_the_speaker(
    hass: HomeAssistant, voxprint: MockConfigEntry, satellites: dict[str, FakeSatellite]
) -> None:
    await switch(hass, ALICE_SWITCH, True)
    await utter(hass, satellites[KITCHEN], audio(1))
    await utter(hass, satellites[BEDROOM], audio(3))
    assert voiceprint(voxprint, "Alice").enrolled == 1
    await switch(hass, ALICE_SWITCH, False)
    await switch(hass, ALICE_SWITCH, True)
    await utter(hass, satellites[BEDROOM], audio(3))
    assert voiceprint(voxprint, "Alice").enrolled == 2


async def test_a_score_landing_while_unloading_saves_nothing(
    hass: HomeAssistant,
    voxprint: MockConfigEntry,
    satellites: dict[str, FakeSatellite],
    fake_app: FakeApp,
    hass_storage: dict[str, Any],
) -> None:
    await switch(hass, ALICE_SWITCH, True)
    await utter(hass, satellites[KITCHEN], audio(1))
    saved = stored(hass_storage)
    fake_app.delay = 0.1
    await satellites[KITCHEN].utter(audio(3))
    unloaded = await hass.config_entries.async_unload(voxprint.entry_id)
    assert unloaded
    await hass.async_block_till_done(wait_background_tasks=True)
    assert stored(hass_storage) == saved
    assert fake_app.audio[-1] == audio(3)
