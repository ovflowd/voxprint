"""Base classes: entities that update on the recognizer's signals, and one device per speaker."""

from __future__ import annotations

from homeassistant.config_entries import ConfigSubentry
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .recognizer import SPEAKERS, Recognizer


class VoxprintEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, recognizer: Recognizer, signal: str | None) -> None:
        self._recognizer = recognizer
        self._signal = signal

    async def async_added_to_hass(self) -> None:
        if self._signal is not None:
            self.async_on_remove(async_dispatcher_connect(self.hass, self._signal, self.async_write_ha_state))


class SpeakerEntity(VoxprintEntity):
    """An entity of one enrolled speaker. Its unique ID and name come from the class's translation key."""

    _updates = True

    def __init__(self, recognizer: Recognizer, subentry: ConfigSubentry) -> None:
        super().__init__(recognizer, recognizer.signal(SPEAKERS) if self._updates else None)
        self._speaker = subentry.subentry_id
        self._attr_unique_id = f"{subentry.subentry_id}-{self._attr_translation_key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, subentry.subentry_id)},
            name=subentry.title,
            entry_type=DeviceEntryType.SERVICE,
        )
