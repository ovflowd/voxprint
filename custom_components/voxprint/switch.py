"""Enrollment: while a speaker's switch is on, utterances at the satellites join their voiceprint."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
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
        async_add_entities([EnrollmentSwitch(entry.runtime_data, subentry)], config_subentry_id=subentry.subentry_id)


class EnrollmentSwitch(SpeakerEntity, SwitchEntity):
    """One speaker at a time. Off after ENROLL_MINUTES and after every restart."""

    # Config entities aren't exposed to voice assistants by default: nobody can enroll by asking for it.
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, recognizer: Recognizer, subentry: ConfigSubentry) -> None:
        super().__init__(recognizer, subentry, "enrollment")

    @property
    def is_on(self) -> bool:
        return self._recognizer.enrolling == self._speaker

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._recognizer.async_set_enrolling(self._speaker)

    async def async_turn_off(self, **kwargs: Any) -> None:
        if self.is_on:
            self._recognizer.async_set_enrolling(None)
