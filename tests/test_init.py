"""Setting up, unloading and repairs: STT is never harmed."""

from __future__ import annotations

from aiohttp import ClientError
from homeassistant.components import stt
from homeassistant.components.assist_pipeline import async_get_pipeline, async_update_pipeline
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er, issue_registry as ir
import pytest
from pytest_homeassistant.common import MockConfigEntry

from custom_components.voxprint import tee
from custom_components.voxprint.const import CONF_SATELLITES, DOMAIN
from fakes import KITCHEN, STT_TEXT, VOICES, FakeApp, FakeSatellite, FakeSTT, audio, utter, voiceprint


async def test_setup_puts_the_tee_on_every_stt_entity(
    hass: HomeAssistant, voxprint: MockConfigEntry, stt_engine: FakeSTT
) -> None:
    assert voxprint.state is ConfigEntryState.LOADED
    assert tee.is_installed(stt_engine)


async def test_unloading_gives_stt_back_untouched(
    hass: HomeAssistant, voxprint: MockConfigEntry, stt_engine: FakeSTT, satellites: dict[str, FakeSatellite]
) -> None:
    unloaded = await hass.config_entries.async_unload(voxprint.entry_id)
    assert unloaded
    assert not tee.is_installed(stt_engine)
    assert tee.PATCHED_ATTR not in stt_engine.__dict__
    await utter(hass, satellites[KITCHEN], audio(1))
    stt_end = [e for e in satellites[KITCHEN].events if e.type == "stt-end"]
    assert stt_end[0].data["stt_output"]["text"] == STT_TEXT


async def test_an_stt_entity_added_later_is_heard_from_its_first_utterance(
    hass: HomeAssistant, voxprint: MockConfigEntry, satellites: dict[str, FakeSatellite], fake_app: FakeApp
) -> None:
    later = FakeSTT()
    later._attr_name = "Later STT"
    later._attr_unique_id = "later-stt"
    await hass.data[stt.DATA_COMPONENT].async_add_entities([later])
    await async_update_pipeline(hass, async_get_pipeline(hass), stt_engine=later.entity_id)
    await utter(hass, satellites[KITCHEN], audio(1))
    assert tee.is_installed(later)
    assert bytes(later.received) == audio(1)
    assert fake_app.audio == [audio(1)]


async def test_setup_works_while_the_app_is_down(
    hass: HomeAssistant, assist: None, fake_app: FakeApp, config_entry: MockConfigEntry
) -> None:
    fake_app.health = ClientError()
    config_entry.add_to_hass(hass)
    set_up = await hass.config_entries.async_setup(config_entry.entry_id)
    assert set_up
    assert config_entry.state is ConfigEntryState.LOADED


async def test_a_home_assistant_without_the_stt_method_gets_a_repair(
    hass: HomeAssistant,
    assist: None,
    fake_app: FakeApp,
    config_entry: MockConfigEntry,
    issue_registry: ir.IssueRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tee, "supported", lambda entity_class: False)
    config_entry.add_to_hass(hass)
    set_up = await hass.config_entries.async_setup(config_entry.entry_id)
    assert set_up
    issue = issue_registry.async_get_issue(DOMAIN, "unsupported_core")
    assert issue.severity is ir.IssueSeverity.ERROR
    monkeypatch.undo()
    reloaded = await hass.config_entries.async_reload(config_entry.entry_id)
    assert reloaded
    assert issue_registry.async_get_issue(DOMAIN, "unsupported_core") is None


async def test_removing_the_integration_removes_its_repairs(
    hass: HomeAssistant,
    voxprint: MockConfigEntry,
    satellites: dict[str, FakeSatellite],
    fake_app: FakeApp,
    issue_registry: ir.IssueRegistry,
) -> None:
    fake_app.replies = [{"model": "another_model", "embedding": [1.0], "voiced_s": 2.0}]
    await utter(hass, satellites[KITCHEN], audio(1))
    assert issue_registry.async_get_issue(DOMAIN, "app_incompatible") is not None
    removed = await hass.config_entries.async_remove(voxprint.entry_id)
    assert removed
    assert issue_registry.async_get_issue(DOMAIN, "app_incompatible") is None


async def test_a_renamed_satellite_is_followed(
    hass: HomeAssistant,
    voxprint: MockConfigEntry,
    satellites: dict[str, FakeSatellite],
    entity_registry: er.EntityRegistry,
) -> None:
    entity_registry.async_update_entity(KITCHEN, new_entity_id="assist_satellite.kitchen_two")
    await hass.async_block_till_done()
    assert voxprint.options[CONF_SATELLITES][0] == "assist_satellite.kitchen_two"
    voiceprint(voxprint, "Alice").add(VOICES[1])
    await utter(hass, satellites[KITCHEN], audio(1))
    assert hass.states.get("sensor.kitchen_speaker").state == "Alice"
    assert (
        entity_registry.async_get("sensor.kitchen_speaker").device_id
        == entity_registry.async_get("assist_satellite.kitchen_two").device_id
    )
