# Entities

## Speaker, one per satellite

`sensor.<satellite>_speaker` sits on the satellite's own device page. If a satellite has no device,
the sensor is named after the satellite instead.

| | |
|---|---|
| State | The name of the speaker who spoke the satellite's last utterance, or `unknown`. An enum sensor: its options are the speakers' names |
| `person` | The speaker's person entity, if they have one |
| `user_id` | That person's Home Assistant user ID, to compare with `context.user_id` |
| `score` | The best speaker's score, from -1 to 1 |
| `scores` | Every enrolled speaker's score, by name |
| `speech_s` | Seconds of speech the app found; at most 6 are used |
| `threshold` | The lowest score that names a speaker |
| `error` | Why nobody was named, or `null` after a score |

The state changes on every request: to `unknown` with `error: listening` when the satellite starts
listening, then to the result. A request that skips listening, because the satellite ran
speech-to-text itself, resets it to `unknown` with `error: not_captured`. So `last_updated` always
moves, and a script can check that the result is recent.

| `error` | Meaning |
|---|---|
| `null` | Scored. The state names the speaker, or `unknown` when nobody reached the threshold |
| `no_utterance` | Nothing heard since Home Assistant or Voxprint started |
| `listening` | The satellite is listening; the result follows |
| `not_captured` | The satellite handled a request whose audio didn't pass the tee, or that arrived as text: see [troubleshooting.md](troubleshooting.md) |
| `too_short` | Under half a second of speech |
| `not_enrolled` | No speaker has a voiceprint yet |
| `ambiguous` | Two speakers both cleared the threshold, within 0.05 of each other |
| `app_unavailable` | The app couldn't be reached, or answered with an error |
| `app_timeout` | The app took longer than 3 seconds |
| `model_mismatch` | The app runs a model this version of the integration doesn't know; a repair says so too |
| `bad_response` | The app's answer wasn't what the integration expects |

## Per speaker

Each speaker is a device of its own.

| Entity | |
|---|---|
| `switch.<speaker>_enrollment` | While on, utterances join this speaker's voiceprint, from the first configured satellite that hears them. Only one speaker at a time; off after 30 minutes and after every restart. A configuration entity, so voice assistants don't get it unless you expose it |
| `sensor.<speaker>_enrolled_utterances` | How many utterances the voiceprint holds, up to 150 |
| `button.<speaker>_reset_voiceprint` | Delete this speaker's voiceprint. Nothing asks for confirmation |

## Repairs

| Repair | |
|---|---|
| Voxprint can't hear this version of Home Assistant | The STT method the tee copies audio from is gone. STT works, nobody is recognized |
| The Voxprint app runs another model | The app's model doesn't match the integration's. Update both |
| Voiceprints were cleared | The stored voiceprints came from another model and were deleted. Enroll again |
