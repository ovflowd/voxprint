"""Entities of one enrolled speaker, grouped on a device per speaker."""

from __future__ import annotations

from homeassistant.config_entries import ConfigSubentry
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .recognizer import Recognizer


class SpeakerEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, recognizer: Recognizer, subentry: ConfigSubentry, key: str) -> None:
        self._recognizer = recognizer
        self._speaker = subentry.subentry_id
        self._attr_translation_key = key
        self._attr_unique_id = f"{subentry.subentry_id}-{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, subentry.subentry_id)},
            name=subentry.title,
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._recognizer.async_add_listener(self.async_write_ha_state))
