"""Reset a speaker's voiceprint, to enroll again from nothing."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigSubentry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import VoxprintConfigEntry
from .const import SUBENTRY_SPEAKER
from .entity import SpeakerEntity
from .recognizer import Recognizer

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: VoxprintConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    for subentry in entry.get_subentries_of_type(SUBENTRY_SPEAKER):
        async_add_entities([ResetButton(entry.runtime_data, subentry)], config_subentry_id=subentry.subentry_id)


class ResetButton(SpeakerEntity, ButtonEntity):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, recognizer: Recognizer, subentry: ConfigSubentry) -> None:
        super().__init__(recognizer, subentry, "reset_voiceprint")

    async def async_press(self) -> None:
        await self._recognizer.async_reset(self._speaker)
