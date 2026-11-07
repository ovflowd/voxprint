"""A speaker sensor per satellite, and an enrolled-utterances count per speaker."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigSubentry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device import async_entity_id_to_device
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import VoxprintConfigEntry
from .const import CONF_PERSON, SUBENTRY_SPEAKER
from .entity import SpeakerEntity, VoxprintEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: VoxprintConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    recognizer = entry.runtime_data
    speakers = entry.get_subentries_of_type(SUBENTRY_SPEAKER)
    sensors = [SatelliteSpeakerSensor(hass, entry, satellite, speakers) for satellite in recognizer.satellites]
    _remove_stale(hass, entry, {sensor.unique_id for sensor in sensors})
    async_add_entities(sensors)
    for subentry in speakers:
        async_add_entities([EnrolledSensor(recognizer, subentry)], config_subentry_id=subentry.subentry_id)


def _remove_stale(hass: HomeAssistant, entry: VoxprintConfigEntry, current: set[str | None]) -> None:
    """Remove the speaker sensors of satellites taken out of the options."""
    registry = er.async_get(hass)
    for registry_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if (
            registry_entry.domain == "sensor"
            and registry_entry.config_subentry_id is None
            and registry_entry.unique_id not in current
        ):
            registry.async_remove(registry_entry.entity_id)


class SatelliteSpeakerSensor(VoxprintEntity, SensorEntity):
    """Who spoke the satellite's last utterance. Its state is the speaker's name, or unknown."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_translation_key = "speaker"

    def __init__(
        self, hass: HomeAssistant, entry: VoxprintConfigEntry, satellite: str, speakers: list[ConfigSubentry]
    ) -> None:
        super().__init__(entry.runtime_data, entry.runtime_data.signal(satellite))
        self._satellite = satellite
        self._names = {subentry.subentry_id: subentry.title for subentry in speakers}
        self._persons = {subentry.subentry_id: subentry.data.get(CONF_PERSON) for subentry in speakers}
        self._attr_options = sorted(self._names.values())
        registry_entry = er.async_get(hass).async_get(satellite)
        self._attr_unique_id = f"{entry.entry_id}-{registry_entry.id if registry_entry else satellite}"
        # On the satellite's own device page, next to its other entities.
        self.device_entry = async_entity_id_to_device(hass, satellite)
        if self.device_entry is None:
            # A satellite without a device: its own name tells the sensors apart.
            state = hass.states.get(satellite)
            self._attr_has_entity_name = False
            self._attr_name = f"{state.name if state else satellite} speaker"

    @property
    def native_value(self) -> str | None:
        speaker = self._recognizer.results[self._satellite].speaker
        return self._names[speaker] if speaker else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        result = self._recognizer.results[self._satellite]
        person = self._persons.get(result.speaker)
        person_state = self.hass.states.get(person) if person else None
        return {
            "person": person,
            "user_id": person_state.attributes.get("user_id") if person_state else None,
            "score": result.score,
            "scores": {self._names[speaker]: score for speaker, score in result.scores.items()},
            "speech_s": result.speech_s,
            "threshold": self._recognizer.threshold,
            "error": result.error,
        }


class EnrolledSensor(SpeakerEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "enrolled"

    @property
    def native_value(self) -> int:
        return self._recognizer.voiceprints[self._speaker].enrolled
