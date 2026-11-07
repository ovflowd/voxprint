"""Voxprint: tells which enrolled person spoke to an Assist satellite.

A tee on every STT entity copies each utterance from a configured satellite into RAM, the Voxprint
app turns it into a speaker embedding, and the satellite's speaker sensor names the enrolled
speaker it matches. STT itself is untouched, and unloading the integration removes the tee at once.
"""

from __future__ import annotations

from functools import partial

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_URL, Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_entity_registry_updated_event

from .client import AppClient
from .const import CONF_SATELLITES, CONF_THRESHOLD, SUBENTRY_SPEAKER
from .recognizer import Recognizer, voiceprint_store

PLATFORMS = [Platform.BUTTON, Platform.SENSOR, Platform.SWITCH]

type VoxprintConfigEntry = ConfigEntry[Recognizer]


async def async_setup_entry(hass: HomeAssistant, entry: VoxprintConfigEntry) -> None:
    recognizer = Recognizer(
        hass,
        entry,
        AppClient(async_get_clientsession(hass), entry.data[CONF_URL]),
        satellites=entry.options[CONF_SATELLITES],
        speakers=[subentry.subentry_id for subentry in entry.get_subentries_of_type(SUBENTRY_SPEAKER)],
        threshold=entry.options[CONF_THRESHOLD],
    )
    entry.async_on_unload(recognizer.async_stop)
    await recognizer.async_start()
    entry.runtime_data = recognizer
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(
        async_track_entity_registry_updated_event(
            hass, recognizer.satellites, partial(_async_satellite_renamed, hass, entry)
        )
    )
    # Options, and speakers added or removed as subentries, apply on a reload.
    entry.async_on_unload(entry.add_update_listener(_async_reload))


@callback
def _async_satellite_renamed(
    hass: HomeAssistant, entry: VoxprintConfigEntry, event: Event[er.EventEntityRegistryUpdatedData]
) -> None:
    """Follow a satellite to its new entity ID; the options would otherwise point at nothing."""
    data = event.data
    if data["action"] != "update" or "old_entity_id" not in data:
        return
    satellites = [data["entity_id"] if s == data["old_entity_id"] else s for s in entry.options[CONF_SATELLITES]]
    hass.config_entries.async_update_entry(entry, options={**entry.options, CONF_SATELLITES: satellites})


async def _async_reload(hass: HomeAssistant, entry: VoxprintConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: VoxprintConfigEntry) -> None:
    # Stopped first, so a score landing while the platforms unload can't save a voiceprint.
    entry.runtime_data.async_stop()
    await hass.config_entries.async_unload_platforms_or_raise(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Removing the integration deletes every voiceprint."""
    await voiceprint_store(hass).async_remove()
