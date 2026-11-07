"""Fakes for the tests: an STT engine, satellites that run the real Assist pipeline, and the Voxprint app.

The fake app answers /v1/embed with an embedding chosen by the audio's first byte, so a test picks who
"speaks" by the bytes it streams: see `audio()` and `VOICES`.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
import math
from typing import Any, ClassVar

from homeassistant.components import stt
from homeassistant.components.assist_pipeline import PipelineStage
from homeassistant.components.assist_satellite import AssistSatelliteConfiguration, AssistSatelliteEntity
from homeassistant.config_entries import ConfigEntry, ConfigSubentryData
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from pytest_homeassistant.test_util.aiohttp import AiohttpClientMocker, AiohttpClientMockResponse
from yarl import URL

from custom_components.voxprint.const import CONF_PERSON, MODEL, SUBENTRY_SPEAKER
from custom_components.voxprint.voiceprint import Voiceprint

APP_URL = "http://voxprint.test:10340"
TEST_DOMAIN = "test"
KITCHEN = "assist_satellite.kitchen"
BEDROOM = "assist_satellite.bedroom"
LOOSE = "assist_satellite.loose"
STT_TEXT = "turn on the lights"
SPEECH_S = 2.0


def unit(*components: float) -> list[float]:
    v = [*components, *[0.0] * (256 - len(components))]
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v]


# The embedding the fake app returns for audio whose first byte is the key.
VOICES: dict[int, list[float]] = {
    1: unit(1.0),  # Alice
    2: unit(0.0, 1.0),  # Bob
    3: unit(1.0, 0.25),  # close to Alice
    4: unit(1.0, 1.0),  # halfway between Alice and Bob
    5: unit(0.0, 0.0, 1.0),  # nobody enrolled
    6: unit(-1.0),  # opposite of Alice, as noise would be
    7: unit(0.5, 1.0),  # like Alice, more like Bob
}


def audio(voice: int, seconds: float = 0.5) -> bytes:
    return bytes([voice]) * int(seconds * 32000)


class FakeSTT(stt.SpeechToTextEntity):
    _attr_name = "Fake STT"
    _attr_unique_id = "fake-stt"
    supported_languages: ClassVar[list[str]] = ["en"]
    supported_formats: ClassVar[list[stt.AudioFormats]] = [stt.AudioFormats.WAV]
    supported_codecs: ClassVar[list[stt.AudioCodecs]] = [stt.AudioCodecs.PCM]
    supported_bit_rates: ClassVar[list[stt.AudioBitRates]] = [stt.AudioBitRates.BITRATE_16]
    supported_sample_rates: ClassVar[list[stt.AudioSampleRates]] = [stt.AudioSampleRates.SAMPLERATE_16000]
    supported_channels: ClassVar[list[stt.AudioChannels]] = [stt.AudioChannels.CHANNEL_MONO]

    def __init__(self) -> None:
        self.received = bytearray()

    @property
    def audio_processing(self) -> stt.SpeechAudioProcessing:
        # No VAD in front of the engine: each test streams exactly the utterance it means.
        return stt.SpeechAudioProcessing(
            requires_external_vad=False, prefers_auto_gain_enabled=False, prefers_noise_reduction_enabled=False
        )

    async def async_process_audio_stream(
        self, metadata: stt.SpeechMetadata, stream: AsyncIterator[bytes]
    ) -> stt.SpeechResult:
        self.received.clear()
        async for chunk in stream:
            self.received += chunk
        return stt.SpeechResult(STT_TEXT, stt.SpeechResultState.SUCCESS)


class FakeSatellite(AssistSatelliteEntity):
    def __init__(self, key: str, with_device: bool = True) -> None:
        self.events: list[Any] = []
        self._attr_name = key.capitalize()
        self._attr_unique_id = f"satellite-{key}"
        if with_device:
            self._attr_has_entity_name = True
            self._attr_name = None
            self._attr_device_info = DeviceInfo(identifiers={(TEST_DOMAIN, key)}, name=key.capitalize())

    def on_pipeline_event(self, event: Any) -> None:
        self.events.append(event)

    def async_get_configuration(self) -> AssistSatelliteConfiguration:
        return AssistSatelliteConfiguration(available_wake_words=[], active_wake_words=[], max_active_wake_words=1)

    async def async_set_configuration(self, config: AssistSatelliteConfiguration) -> None:
        pass

    async def utter(self, voice: bytes) -> None:
        """One utterance through the real pipeline, as a satellite sends it."""

        async def stream() -> AsyncIterator[bytes]:
            for i in range(0, len(voice), 1024):
                yield voice[i : i + 1024]

        await self.async_accept_pipeline_from_satellite(
            stream(), start_stage=PipelineStage.STT, end_stage=PipelineStage.STT
        )


class FakeApp:
    """The Voxprint app's HTTP API. `replies` overrides the next answers in order."""

    def __init__(self, aioclient_mock: AiohttpClientMocker) -> None:
        self.health: dict[str, Any] | Exception = {"ok": True, "api": 1, "model": MODEL, "version": "0.1.0"}
        self.replies: list[dict[str, Any] | list[float] | Exception] = []
        self.audio: list[bytes] = []
        self.delay = 0.0
        aioclient_mock.get(f"{APP_URL}/health", side_effect=self._health)
        aioclient_mock.post(f"{APP_URL}/v1/embed", side_effect=self._embed)

    async def _health(self, method: str, url: URL, data: Any) -> AiohttpClientMockResponse:
        if isinstance(self.health, Exception):
            return AiohttpClientMockResponse(method, url, exc=self.health)
        return AiohttpClientMockResponse(method, url, json=self.health)

    async def _embed(self, method: str, url: URL, data: bytes) -> AiohttpClientMockResponse:
        self.audio.append(data)
        if self.delay:
            await asyncio.sleep(self.delay)
        reply = self.replies.pop(0) if self.replies else self.reply_for(data)
        if isinstance(reply, Exception):
            return AiohttpClientMockResponse(method, url, exc=reply)
        return AiohttpClientMockResponse(method, url, json=reply)

    @staticmethod
    def reply_for(data: bytes) -> dict[str, Any]:
        return {"model": MODEL, "embedding": VOICES[data[0]], "voiced_s": SPEECH_S, "total_s": SPEECH_S, "ms": 20}


def speaker(title: str, person: str | None = None) -> ConfigSubentryData:
    return ConfigSubentryData(
        data={CONF_PERSON: person} if person else {},
        subentry_type=SUBENTRY_SPEAKER,
        title=title,
        unique_id=title.casefold(),
    )


def subentry_id(entry: ConfigEntry, title: str) -> str:
    return next(s.subentry_id for s in entry.subentries.values() if s.title == title)


def voiceprint(entry: ConfigEntry, title: str) -> Voiceprint:
    return entry.runtime_data.voiceprints[subentry_id(entry, title)]


async def utter(hass: HomeAssistant, satellite: FakeSatellite, voice: bytes) -> None:
    await satellite.utter(voice)
    await hass.async_block_till_done(wait_background_tasks=True)
