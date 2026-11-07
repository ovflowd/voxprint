# Troubleshooting

**The integration can't connect to the app.** Check that the app is running and that its log ends
with `self-test norm 1.0`. On Home Assistant OS, the URL is `http://<hostname>:10340`, with the
hostname from the app's info page (dashes, not underscores). Under Docker, check the port mapping and
that Home Assistant can reach that address.

**"The app at this URL runs a different model or API version."** The app and the integration are from
releases that don't match. Update both.

**The speaker sensor stays at `error: listening`.** The satellite started listening and the pipeline
never got as far as the STT engine, or the app's answer is still on its way. If it lasts, check the
satellite's pipeline in Settings → Voice assistants → the pipeline → Debug.

**`not_captured`.** The satellite handled a request, but its audio never reached Voxprint's tee:
- the pipeline uses a legacy STT provider that isn't an entity: it can't be heard;
- the satellite runs speech-to-text itself, so the request reaches Home Assistant as text;
- a Home Assistant update changed the STT method the tee relies on. A repair says so; update Voxprint.

**`app_unavailable` or `app_timeout`.** The app is stopped, restarting, unreachable, or slower than 3
seconds. STT is not affected. Turn on the app's *Watchdog*, and check its log at `debug` level for how
long each utterance takes.

**`too_short` on short commands.** Under half a second of speech is never scored. Speak a full
sentence when it matters.

**Someone is recognized who shouldn't be.** Raise the threshold, following
[calibration](enrollment.md#calibrate). If their scores overlap an enrolled speaker's, speaker
recognition can't tell them apart in your room.

**An enrolled speaker is turned away too often.** Enroll 10 to 15 more utterances at the satellite they
use, at their usual distance. Check `speech_s`: short utterances score lower.

**`ambiguous`.** Two enrolled speakers both cleared the threshold, within 0.05 of each other. Enroll
both with more utterances.

**Enrolled utterances stays at 1.** The first utterance wasn't the speaker's voice, so the rest don't
match it. Press **Reset voiceprint** and enroll again, alone.

**Diagnostics.** Download them from the integration's page and attach them to an issue: they number
the speakers and leave out names, persons, user IDs, addresses and embeddings. Never attach a
recording or a file from `.storage`.
