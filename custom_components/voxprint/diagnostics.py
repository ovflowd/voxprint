"""Diagnostics without speaker names, persons, the app's address or any embedding."""

from __future__ import annotations

from typing import Any

from homeassistant.components import stt
from homeassistant.core import HomeAssistant

from . import VoxprintConfigEntry
from .client import AppError
from .const import CONF_PERSON, MODEL, SUBENTRY_SPEAKER
from .tee import is_installed


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: VoxprintConfigEntry) -> dict[str, Any]:
    recognizer = entry.runtime_data
    try:
        app: dict[str, Any] = await recognizer.client.health()
    except AppError as err:
        app = {"error": err.code}
    subentries = entry.get_subentries_of_type(SUBENTRY_SPEAKER)
    # Speakers are numbered, so names stay out of a file that gets attached to public issues.
    numbers = {subentry.subentry_id: f"speaker_{n}" for n, subentry in enumerate(subentries, start=1)}
    return {
        "options": dict(entry.options),
        "model": MODEL,
        "app": app,
        "speakers": {
            numbers[subentry.subentry_id]: {
                "enrolled": recognizer.voiceprints[subentry.subentry_id].enrolled,
                "enrolling": recognizer.enrolling == subentry.subentry_id,
                "has_person": CONF_PERSON in subentry.data,
            }
            for subentry in subentries
        },
        "results": {
            satellite: {
                "speaker": numbers[result.speaker] if result.speaker else None,
                "score": result.score,
                "scores": {numbers[speaker]: score for speaker, score in result.scores.items()},
                "speech_s": result.speech_s,
                "error": result.error,
            }
            for satellite, result in recognizer.results.items()
        },
        "tee": {
            entity_id: entity is not None and is_installed(entity)
            for entity_id in hass.states.async_entity_ids(stt.DOMAIN)
            for entity in [stt.async_get_speech_to_text_entity(hass, entity_id)]
        },
    }
