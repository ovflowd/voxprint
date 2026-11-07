"""Setting Voxprint up, reconfiguring it, its options, and the speakers."""

from __future__ import annotations

from typing import Any

from aiohttp import ClientError
from homeassistant.components.hassio import HassioNotReadyError
from homeassistant.config_entries import SOURCE_RECONFIGURE
from homeassistant.const import CONF_NAME, CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant.common import MockConfigEntry, get_schema_suggested_value

from custom_components.voxprint.const import API_VERSION, CONF_PERSON, CONF_SATELLITES, CONF_THRESHOLD, MODEL
from fakes import (
    APP_URL,
    BEDROOM,
    KITCHEN,
    LOOSE,
    FakeApp,
    FakeSatellite,
    add_speaker,
    audio,
    start_flow,
    subentry_id,
    switch,
    utter,
    voiceprint,
)

ALL = [KITCHEN, BEDROOM, LOOSE]


def suggested(result: dict[str, Any], key: str) -> Any:
    return get_schema_suggested_value(result["data_schema"].schema, key)


async def test_setup_checks_the_app_and_listens_to_every_satellite_by_default(
    hass: HomeAssistant, assist: None, fake_app: FakeApp
) -> None:
    result = await start_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert sorted(suggested(result, CONF_SATELLITES)) == sorted(ALL)
    assert suggested(result, CONF_URL) == "http://localhost:10340"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: f"{APP_URL}/", CONF_SATELLITES: [KITCHEN]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Voxprint"
    assert result["data"] == {CONF_URL: APP_URL}
    assert result["options"] == {CONF_SATELLITES: [KITCHEN], CONF_THRESHOLD: 0.5}


async def test_on_home_assistant_os_the_installed_app_is_suggested(
    hass: HomeAssistant, assist: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("custom_components.voxprint.config_flow.is_hassio", lambda hass: True)
    monkeypatch.setattr(
        "homeassistant.components.hassio.get_apps_list",
        lambda hass: [{"slug": "core_ssh"}, {"slug": "5c53de3b_voxprint"}],
    )
    result = await start_flow(hass)
    assert suggested(result, CONF_URL) == "http://5c53de3b-voxprint:10340"


async def test_a_supervisor_that_is_not_ready_falls_back_to_a_host_port(
    hass: HomeAssistant, assist: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def not_ready(hass: HomeAssistant) -> list[dict[str, Any]]:
        raise HassioNotReadyError

    monkeypatch.setattr("custom_components.voxprint.config_flow.is_hassio", lambda hass: True)
    monkeypatch.setattr("homeassistant.components.hassio.get_apps_list", not_ready)
    result = await start_flow(hass)
    assert suggested(result, CONF_URL) == "http://localhost:10340"


async def test_setup_needs_a_satellite(hass: HomeAssistant) -> None:
    result = await start_flow(hass)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_satellites"


@pytest.mark.parametrize(
    ("health", "user_input", "error"),
    [
        (ClientError(), {CONF_URL: APP_URL, CONF_SATELLITES: [KITCHEN]}, {"base": "cannot_connect"}),
        (
            {"ok": True, "api": 2, "model": "x"},
            {CONF_URL: APP_URL, CONF_SATELLITES: [KITCHEN]},
            {"base": "app_incompatible"},
        ),
        (None, {CONF_URL: APP_URL, CONF_SATELLITES: []}, {CONF_SATELLITES: "no_satellite_selected"}),
    ],
)
async def test_setup_shows_what_is_wrong_and_recovers(
    hass: HomeAssistant,
    assist: None,
    fake_app: FakeApp,
    health: Any,
    user_input: dict[str, Any],
    error: dict[str, str],
) -> None:
    good = fake_app.health
    if health is not None:
        fake_app.health = health
    result = await start_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == error
    fake_app.health = good
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: APP_URL, CONF_SATELLITES: [KITCHEN]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_only_one_instance(hass: HomeAssistant, voxprint: MockConfigEntry) -> None:
    result = await start_flow(hass)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_reconfigure_changes_the_app_url(
    hass: HomeAssistant, voxprint: MockConfigEntry, fake_app: FakeApp
) -> None:
    result = await voxprint.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    fake_app.health = {"ok": True, "api": 1, "model": "x"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_URL: APP_URL})
    assert result["errors"] == {"base": "app_incompatible"}
    fake_app.health = {"ok": True, "api": API_VERSION, "model": MODEL}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_URL: f"{APP_URL}//"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert voxprint.data[CONF_URL] == APP_URL
    assert voxprint.source != SOURCE_RECONFIGURE


async def test_options_change_satellites_and_threshold(hass: HomeAssistant, voxprint: MockConfigEntry) -> None:
    result = await hass.config_entries.options.async_init(voxprint.entry_id)
    assert sorted(suggested(result, CONF_SATELLITES)) == sorted(ALL)
    assert suggested(result, CONF_THRESHOLD) == 0.5
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SATELLITES: [], CONF_THRESHOLD: 0.6}
    )
    assert result["errors"] == {CONF_SATELLITES: "no_satellite_selected"}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SATELLITES: [KITCHEN], CONF_THRESHOLD: 0.6}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert voxprint.runtime_data.threshold == 0.6
    assert hass.states.get("sensor.bedroom_speaker") is None
    assert er.async_get(hass).async_get("sensor.bedroom_speaker") is None
    assert hass.states.get("sensor.kitchen_speaker").attributes["threshold"] == 0.6


async def test_a_speaker_can_be_added_with_or_without_a_person(hass: HomeAssistant, voxprint: MockConfigEntry) -> None:
    result = await add_speaker(hass, voxprint, {CONF_NAME: " Carol ", CONF_PERSON: "person.carol"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    result = await add_speaker(hass, voxprint, {CONF_NAME: "Dave"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    carol = voxprint.subentries[subentry_id(voxprint, "Carol")]
    assert carol.data == {CONF_PERSON: "person.carol"}
    assert voxprint.subentries[subentry_id(voxprint, "Dave")].data == {}
    assert hass.states.get("switch.carol_enrollment").state == "off"
    assert hass.states.get("sensor.kitchen_speaker").attributes["options"] == ["Alice", "Bob", "Carol", "Dave"]


@pytest.mark.parametrize(("name", "error"), [("  ", "name_empty"), ("alice", "name_taken")])
async def test_a_speaker_needs_a_name_of_their_own(
    hass: HomeAssistant, voxprint: MockConfigEntry, name: str, error: str
) -> None:
    result = await add_speaker(hass, voxprint, {CONF_NAME: name})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_NAME: error}


async def test_renaming_a_speaker_keeps_their_voiceprint(
    hass: HomeAssistant, voxprint: MockConfigEntry, satellites: dict[str, FakeSatellite]
) -> None:
    await switch(hass, "switch.bob_enrollment", True)
    await utter(hass, satellites[KITCHEN], audio(2))
    bob = subentry_id(voxprint, "Bob")
    result = await voxprint.start_subentry_reconfigure_flow(hass, bob)
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {CONF_NAME: "Alice"})
    assert result["errors"] == {CONF_NAME: "name_taken"}
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {CONF_NAME: "Robert", CONF_PERSON: "person.robert"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert voxprint.subentries[bob].title == "Robert"
    assert voxprint.subentries[bob].data == {CONF_PERSON: "person.robert"}
    assert voiceprint(voxprint, "Robert").enrolled == 1
