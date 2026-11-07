"""Score each satellite utterance against the enrolled voiceprints and publish who spoke.

It fails closed. A satellite's result is reset when it starts listening, and only that utterance's
score can name a speaker. STT is never delayed: the tee only copies audio, and scoring runs as a
background task that starts when the audio ends, while the STT engine is still transcribing.

Which satellite an STT stream comes from: a satellite turns `listening` inside its pipeline task,
right before that task calls the STT engine (assist_satellite/entity.py, assist_pipeline). State
changes are dispatched synchronously, so the state listener records the running task, and the tee
claims a stream only when it runs in that same task. Audio from anywhere else (the companion app,
the browser, a satellite that isn't configured) is never captured.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
import logging
from typing import TYPE_CHECKING, Any
import weakref

from homeassistant.components import stt
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.helpers.storage import Store

from . import tee
from .client import AppClient, AppError
from .const import (
    AMBIGUITY_MARGIN,
    DOMAIN,
    ENROLL_FLOOR,
    ENROLL_MINUTES,
    MIN_SPEECH_S,
    MODEL,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .voiceprint import Voiceprint

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)

LISTENING = "listening"
PROCESSING = "processing"
DOCS_URL = "https://github.com/ovflowd/voxprint/blob/main/docs/troubleshooting.md"


@dataclass(frozen=True, slots=True)
class Result:
    """The outcome of a satellite's last utterance. `speaker` is a speaker's subentry ID."""

    error: str | None
    speaker: str | None = None
    score: float | None = None
    scores: dict[str, float] = field(default_factory=dict)
    speech_s: float | None = None


def voiceprint_store(hass: HomeAssistant) -> Store[dict[str, Any]]:
    return Store(hass, STORAGE_VERSION, STORAGE_KEY, private=True, atomic_writes=True)


class Recognizer:
    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: AppClient,
        satellites: list[str],
        speakers: list[str],
        threshold: float,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.client = client
        self.satellites = list(satellites)
        self.threshold = threshold
        self.voiceprints = {speaker: Voiceprint() for speaker in speakers}
        self.results = {satellite: Result("no_utterance") for satellite in self.satellites}
        self.enrolling: str | None = None
        self._store = voiceprint_store(hass)
        self._listeners: list[Callable[[], None]] = []
        self._seq = dict.fromkeys(self.satellites, 0)
        self._captured = dict.fromkeys(self.satellites, 0)
        self._pending: weakref.WeakKeyDictionary[asyncio.Task[Any], tuple[str, int]] = weakref.WeakKeyDictionary()
        self._teed: weakref.WeakSet[stt.SpeechToTextEntity] = weakref.WeakSet()
        self._unsub_satellites: CALLBACK_TYPE | None = None
        self._cancel_enroll: CALLBACK_TYPE | None = None
        self._enroll_satellite: str | None = None
        self._save_lock = asyncio.Lock()
        self._stopped = False

    async def async_start(self) -> None:
        if not tee.supported(stt.SpeechToTextEntity):
            self._create_issue("unsupported_core", ir.IssueSeverity.ERROR)
        else:
            ir.async_delete_issue(self.hass, DOMAIN, "unsupported_core")
        await self._async_load()
        self._unsub_satellites = async_track_state_change_event(self.hass, self.satellites, self._on_satellite)
        self._ensure_tees()

    async def async_stop(self) -> None:
        """Stop hearing anything, and wait for a save in progress, so nothing writes the voiceprints afterwards."""
        if self._stopped:
            return
        self._stopped = True
        self.enrolling = None
        for satellite in self._seq:
            self._seq[satellite] += 1
        if self._unsub_satellites:
            self._unsub_satellites()
        if self._cancel_enroll:
            self._cancel_enroll()
        for entity in list(self._teed):
            tee.uninstall(entity)
        self._teed.clear()
        async with self._save_lock:
            pass

    @callback
    def async_add_listener(self, update: Callable[[], None]) -> CALLBACK_TYPE:
        self._listeners.append(update)
        return lambda: self._listeners.remove(update)

    @callback
    def _notify(self) -> None:
        for update in list(self._listeners):
            update()

    # storage -------------------------------------------------------------------

    async def _async_load(self) -> None:
        data = await self._store.async_load()
        data = data or {}
        stored: dict[str, list[str]] = data.get("speakers", {})
        if stored and data.get("model") != MODEL:
            # Embeddings from another model can't be compared with this one's.
            _LOGGER.warning("Voiceprints made with %s were cleared; enroll again", data.get("model"))
            self._create_issue("voiceprints_cleared", ir.IssueSeverity.WARNING, {"model": str(data.get("model"))})
            await self._async_save()
            return
        for speaker, samples in stored.items():
            if speaker in self.voiceprints:
                self.voiceprints[speaker] = Voiceprint.from_json(samples)
        if set(stored) - set(self.voiceprints):
            await self._async_save()

    async def _async_save(self) -> None:
        async with self._save_lock:
            if self._stopped:
                return
            await self._store.async_save(
                {"model": MODEL, "speakers": {speaker: vp.to_json() for speaker, vp in self.voiceprints.items()}}
            )

    # capture -------------------------------------------------------------------

    @callback
    def _ensure_tees(self) -> None:
        """Put the tee on every STT entity, including ones added or re-created since the last utterance."""
        for entity_id in self.hass.states.async_entity_ids(stt.DOMAIN):
            entity = stt.async_get_speech_to_text_entity(self.hass, entity_id)
            if entity is None or entity in self._teed:
                continue
            if tee.install(entity, self._on_start, self._on_audio_end, self._on_done):
                self._teed.add(entity)

    @callback
    def _on_satellite(self, event: Event[EventStateChangedData]) -> None:
        satellite = event.data["entity_id"]
        old, new = event.data["old_state"], event.data["new_state"]
        if new is not None and new.state == LISTENING:
            self._seq[satellite] += 1
            if (task := asyncio.current_task()) is not None:
                self._pending[task] = (satellite, self._seq[satellite])
            self._ensure_tees()
            self._publish(satellite, Result("listening"))
        elif old is not None and old.state == LISTENING:
            if self._captured[satellite] != self._seq[satellite]:
                self._publish(satellite, Result("not_captured"))
        elif new is not None and new.state == PROCESSING and (old is None or old.state != PROCESSING):
            # A run that starts past speech-to-text, such as STT on the satellite itself: there is no audio to
            # score, and the previous verdict must not stand for this request.
            self._seq[satellite] += 1
            self._publish(satellite, Result("not_captured"))

    @callback
    def _on_start(self, metadata: stt.SpeechMetadata) -> tee.Capture | None:
        task = asyncio.current_task()
        claim = self._pending.pop(task, None) if task is not None else None
        if claim is None:
            return None
        satellite, seq = claim
        if not _is_16k_mono_pcm(metadata):
            _LOGGER.debug("%s sent audio Voxprint can't read: %s", satellite, metadata)
            return None
        self._captured[satellite] = seq
        return tee.Capture(satellite, seq, self.enrolling)

    @callback
    def _on_audio_end(self, cap: tee.Capture) -> None:
        if cap.scored or self._stopped:
            return
        cap.scored = True
        pcm = bytes(cap.buf)
        cap.buf.clear()
        self.entry.async_create_background_task(
            self.hass, self._async_score(pcm, cap.satellite, cap.seq, cap.enrolling), f"{DOMAIN} score"
        )

    @callback
    def _on_done(self, cap: tee.Capture) -> None:
        # The engine stopped reading before the audio ended.
        self._on_audio_end(cap)

    # scoring -------------------------------------------------------------------

    async def _async_score(self, pcm: bytes, satellite: str, seq: int, enrolling: str | None) -> None:
        """Score one utterance. `enrolling` is the speaker who was enrolling when it was spoken."""
        try:
            reply: dict[str, Any] = await self.client.embed(pcm)
        except AppError as err:
            _LOGGER.debug("Voxprint app: %s", err)
            reply = {"error": err.code}
        finally:
            del pcm
        if self._stopped or seq != self._seq[satellite]:
            return
        try:
            result = self._decide(reply)
        except (KeyError, TypeError, ValueError) as err:
            _LOGGER.warning("Unexpected reply from the Voxprint app: %r", err)
            result = Result("bad_response")
        self._publish(satellite, result)
        if (
            enrolling is not None
            and enrolling == self.enrolling
            and result.error in (None, "not_enrolled", "ambiguous")
        ):
            await self._async_enroll(enrolling, satellite, reply["embedding"], result)

    def _decide(self, reply: dict[str, Any]) -> Result:
        speech_s = reply.get("voiced_s")
        if reply.get("error"):
            return Result(str(reply["error"]), speech_s=speech_s)
        if reply.get("model") != MODEL:
            self._create_issue("app_incompatible", ir.IssueSeverity.ERROR, {"model": str(reply.get("model"))})
            return Result("model_mismatch", speech_s=speech_s)
        ir.async_delete_issue(self.hass, DOMAIN, "app_incompatible")
        if "embedding" not in reply or float(speech_s) < MIN_SPEECH_S:
            return Result("too_short", speech_s=speech_s)
        embedding = reply["embedding"]
        scores = {
            speaker: round(score, 3)
            for speaker, vp in self.voiceprints.items()
            if (score := vp.score(embedding)) is not None
        }
        if not scores:
            return Result("not_enrolled", speech_s=speech_s)
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        best, score = ranked[0]
        if score < self.threshold:
            return Result(None, score=score, scores=scores, speech_s=speech_s)
        if len(ranked) > 1 and ranked[1][1] >= self.threshold and score - ranked[1][1] < AMBIGUITY_MARGIN:
            return Result("ambiguous", score=score, scores=scores, speech_s=speech_s)
        return Result(None, speaker=best, score=score, scores=scores, speech_s=speech_s)

    @callback
    def _publish(self, satellite: str, result: Result) -> None:
        self.results[satellite] = result
        self._notify()

    # enrollment ----------------------------------------------------------------

    @callback
    def async_set_enrolling(self, speaker: str | None) -> None:
        """Enroll one speaker for ENROLL_MINUTES, or stop. Only one speaker enrolls at a time."""
        if self._cancel_enroll:
            self._cancel_enroll()
            self._cancel_enroll = None
        self.enrolling = speaker
        self._enroll_satellite = None
        if speaker is not None:
            self._cancel_enroll = async_call_later(self.hass, ENROLL_MINUTES * 60, self._enroll_timeout)
        self._notify()

    @callback
    def _enroll_timeout(self, _now: Any) -> None:
        self._cancel_enroll = None
        self.async_set_enrolling(None)

    async def _async_enroll(self, speaker: str, satellite: str, embedding: list[float], result: Result) -> None:
        # One satellite per session, the first that hears the speaker: someone talking to another satellite in
        # another room can't join. A speaker's first utterance is taken as it is, since there is nothing of
        # theirs to compare it with, and someone who sounds like an enrolled speaker must still be able to
        # enroll. Being alone is the guard.
        if self._enroll_satellite not in (None, satellite):
            _LOGGER.info("Not enrolled: this enrollment listens to %s", self._enroll_satellite)
            return
        own = result.scores.get(speaker)
        if own is not None and own < ENROLL_FLOOR:
            _LOGGER.info("Not enrolled: %.3f is too unlike this speaker's voiceprint", own)
            return
        if own is not None and any(
            score >= self.threshold and score > own for other, score in result.scores.items() if other != speaker
        ):
            _LOGGER.info("Not enrolled: the utterance matches another speaker better")
            return
        self._enroll_satellite = satellite
        self.voiceprints[speaker].add(embedding)
        self._notify()
        await self._async_save()

    async def async_reset(self, speaker: str) -> None:
        self.voiceprints[speaker].clear()
        self._notify()
        await self._async_save()

    # repairs -------------------------------------------------------------------

    @callback
    def _create_issue(
        self, issue_id: str, severity: ir.IssueSeverity, placeholders: dict[str, str] | None = None
    ) -> None:
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            issue_id,
            config_entry_id=self.entry.entry_id,
            is_fixable=False,
            learn_more_url=DOCS_URL,
            severity=severity,
            translation_key=issue_id,
            translation_placeholders=placeholders,
        )


def _is_16k_mono_pcm(metadata: stt.SpeechMetadata) -> bool:
    return (
        metadata.codec == stt.AudioCodecs.PCM
        and metadata.sample_rate == stt.AudioSampleRates.SAMPLERATE_16000
        and metadata.bit_rate == stt.AudioBitRates.BITRATE_16
        and metadata.channel == stt.AudioChannels.CHANNEL_MONO
    )
