"""Fixtures: the Assist stack with fake satellites, the fake app, and a set-up Voxprint entry."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

from homeassistant.components.assist_pipeline import async_get_pipeline, async_update_pipeline
from homeassistant.config_entries import ConfigEntry, ConfigFlow
from homeassistant.const import CONF_URL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant.common import (
    MockConfigEntry,
    MockModule,
    mock_config_flow,
    mock_integration,
    mock_platform,
    setup_test_component_platform,
)
from pytest_homeassistant.test_util.aiohttp import AiohttpClientMocker

from custom_components.voxprint.const import CONF_SATELLITES, CONF_THRESHOLD, DOMAIN
from fakes import APP_URL, BEDROOM, KITCHEN, LOOSE, TEST_DOMAIN, FakeApp, FakeSatellite, FakeSTT, speaker


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Every test loads the integration from custom_components/."""


@pytest.fixture
def fake_app(aioclient_mock: AiohttpClientMocker) -> FakeApp:
    return FakeApp(aioclient_mock)


@pytest.fixture
def stt_engine() -> FakeSTT:
    return FakeSTT()


@pytest.fixture
def satellites() -> dict[str, FakeSatellite]:
    return {
        KITCHEN: FakeSatellite("kitchen"),
        BEDROOM: FakeSatellite("bedroom"),
        LOOSE: FakeSatellite("loose", with_device=False),
    }


@pytest.fixture
async def assist(
    hass: HomeAssistant,
    stt_engine: FakeSTT,
    satellites: dict[str, FakeSatellite],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The Assist stack, with the fake engine as the preferred pipeline's STT."""
    monkeypatch.setattr("homeassistant.components.tts.DEFAULT_CACHE_DIR", str(tmp_path / "tts"))
    set_up = await async_setup_component(hass, "homeassistant", {})
    assert set_up

    async def setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
        await hass.config_entries.async_forward_entry_setups(entry, [Platform.STT, Platform.ASSIST_SATELLITE])

    mock_integration(hass, MockModule(TEST_DOMAIN, async_setup_entry=setup_entry))
    setup_test_component_platform(hass, Platform.STT, [stt_engine], from_config_entry=True)
    setup_test_component_platform(hass, Platform.ASSIST_SATELLITE, list(satellites.values()), from_config_entry=True)
    mock_platform(hass, f"{TEST_DOMAIN}.config_flow", Mock())
    set_up = await async_setup_component(hass, "assist_pipeline", {})
    assert set_up
    with mock_config_flow(TEST_DOMAIN, ConfigFlow):
        entry = MockConfigEntry(domain=TEST_DOMAIN)
        entry.add_to_hass(hass)
        set_up = await hass.config_entries.async_setup(entry.entry_id)
        assert set_up
    await async_update_pipeline(hass, async_get_pipeline(hass), stt_engine=stt_engine.entity_id, stt_language="en")
    hass.states.async_set("person.alice", "home", {"user_id": "user-alice", "friendly_name": "Alice"})
    await hass.async_block_till_done()


@pytest.fixture
def config_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Voxprint",
        data={CONF_URL: APP_URL},
        options={CONF_SATELLITES: [KITCHEN, BEDROOM, LOOSE], CONF_THRESHOLD: 0.5},
        subentries_data=[speaker("Alice", "person.alice"), speaker("Bob")],
    )


@pytest.fixture
async def voxprint(
    hass: HomeAssistant, assist: None, fake_app: FakeApp, config_entry: MockConfigEntry
) -> MockConfigEntry:
    config_entry.add_to_hass(hass)
    set_up = await hass.config_entries.async_setup(config_entry.entry_id)
    assert set_up
    await hass.async_block_till_done()
    return config_entry
