# voxprint

[![CI](https://github.com/ovflowd/voxprint/actions/workflows/ci.yml/badge.svg)](https://github.com/ovflowd/voxprint/actions/workflows/ci.yml)
[![Validate](https://github.com/ovflowd/voxprint/actions/workflows/validate.yml/badge.svg)](https://github.com/ovflowd/voxprint/actions/workflows/validate.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Speaker recognition for Home Assistant Assist: tells which enrolled person spoke to a voice
satellite, locally.

Assist knows who is logged in to the app, but not who is talking to the satellite in the kitchen.
Voxprint gives each satellite a speaker sensor, so a script can keep calendars, reminders or anything
else private for the right voice. It listens alongside your speech-to-text instead of replacing it, so
it works with Home Assistant Cloud, Wyoming or any other STT engine, and it never stores audio.

> [!WARNING]
> Speaker recognition is a convenience, not a lock. A similar voice or a recording of an enrolled
> person can pass, and Voxprint can't tell a recording from a person. Don't put locks, alarms or money
> behind a voice alone. [docs/accuracy.md](docs/accuracy.md) has the numbers.

## What you need

- Home Assistant 2026.11 or later, with an Assist satellite: a Home Assistant Voice PE, an ESPHome or
  Wyoming satellite, or any other `assist_satellite` entity.
- An STT engine that is an entity, which all current ones are.
- Home Assistant OS on an amd64 or aarch64 machine, for the app. Elsewhere, run the app's image with
  Docker: [docs/installation.md](docs/installation.md).

## Install

Both parts come from this repository.

1. **The app.** Settings → Apps → App store → ⋮ → Repositories, add
   `https://github.com/ovflowd/voxprint`, then install **Voxprint** and start it.
   [![Add the repository](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fovflowd%2Fvoxprint)
2. **The integration.** In the Marketplace (HACS), ⋮ → Custom repositories, add the same URL as an
   *Integration*, download **Voxprint**, and restart Home Assistant.
3. Settings → Devices & services → Add integration → **Voxprint**. The app's address is filled in;
   choose the satellites to listen to.

## Use it

1. On the Voxprint page, **Add speaker**: a name, and optionally the person they are.
2. Turn on that speaker's **Enrollment** switch and have them talk to a satellite, alone, for about
   three minutes: 35 or so ordinary requests. The switch turns itself off after 30 minutes.
3. Each satellite now has a **Speaker** sensor. Its state is the name of whoever spoke the last
   utterance, or `unknown`.
4. [Calibrate the threshold](docs/enrollment.md#calibrate) with your own satellites and voices.

A script that Assist calls can then answer only the right person at a satellite:

```yaml
condition: template
value_template: >-
  {{ not context.user_id
     and states('sensor.kitchen_satellite_speaker') == 'Alice'
     and now() - states.sensor.kitchen_satellite_speaker.last_updated < timedelta(seconds=30) }}
```

The sensor says who spoke at that satellite, not who started the script, so configure every satellite
in your home. [docs/automations.md](docs/automations.md) explains the rules, and has a script that
accepts either a logged-in user or a recognized voice.

## Entities

| Entity | |
|---|---|
| `sensor.<satellite>_speaker` | On each satellite's device: who spoke its last utterance, with the scores and why nobody was named |
| `switch.<speaker>_enrollment` | While on, that speaker's utterances join their voiceprint |
| `sensor.<speaker>_enrolled_utterances` | How many utterances their voiceprint holds |
| `button.<speaker>_reset_voiceprint` | Forget their voiceprint, to enroll again |

[docs/entities.md](docs/entities.md) lists every attribute and error.

## How it works

The integration copies each utterance from a configured satellite in RAM as it streams to the STT
engine, unchanged. When the speaker stops, the copy goes to the app, which turns it into a voice
embedding with WeSpeaker ResNet34-LM. The integration compares that with each speaker's voiceprint,
while the STT engine is still transcribing. It fails closed: the sensor is reset as soon as a satellite
listens, and only that utterance's own score can name anyone. If the app is down, slow or unsure, the
speaker is `unknown` and STT carries on as before. [docs/how-it-works.md](docs/how-it-works.md) has
the details.

## Privacy

- Only audio from the configured satellites is captured, in RAM, and it is dropped once scored. Audio
  from the companion app or the browser is never captured.
- The audio goes to the app over Home Assistant's internal network and nowhere else. The app keeps
  nothing and needs no internet after it is built.
- Voiceprints are embeddings, never audio: at most 150 per speaker, in `/config/.storage/voxprint`
  with mode 0600. Removing a speaker or the integration deletes them; a speaker removed while Voxprint
  is disabled is deleted the next time it loads.

## Troubleshooting

See [docs/troubleshooting.md](docs/troubleshooting.md). After each Home Assistant update, check that the
speaker sensors still update: Voxprint relies on an internal STT method, and raises a repair if it
disappears.

## Related projects

[wyoming-voice-match](https://github.com/jxlarrea/wyoming-voice-match) is a Wyoming STT proxy that
checks the speaker and drops other voices before transcription. Voxprint keeps your STT engine,
Home Assistant Cloud included, and only reports who spoke.

## Development

```bash
uv sync
(cd app && uv sync)
uv run pytest
uv run ruff check .
```

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE). The app downloads one model when it is built, WeSpeaker ResNet34-LM trained on
VoxCeleb, licensed CC BY 4.0; [NOTICE](NOTICE) has the attribution. Voxprint isn't affiliated with
Home Assistant or the Open Home Foundation.
