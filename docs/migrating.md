# Migrating from the prototype

Voxprint grew out of a prototype for one Home Assistant Voice PE and one speaker: a local app,
`aelita_voiceprint`, and a custom integration, `aelita_voice_match`, that teed
`stt.home_assistant_cloud`. This page moves that install to Voxprint. Nothing here is automatic; do it
when you choose.

The model, the audio preprocessing and the embedding format are the same, so scores, the threshold
and the enrolled voiceprint all carry over. Removing the prototype deletes its voiceprint file, so copy
it first (step 3); step 6 moves it into Voxprint instead of enrolling again.

## What changes

| Prototype | Voxprint |
|---|---|
| `sensor.aelita_voice_match`: state = score, attribute `speaker: claudio` | `sensor.home_assistant_voice_pe_speaker`: state = the speaker's name, attributes `user_id`, `person`, `score`, `scores` |
| `switch.aelita_voice_enrolment` | `switch.<speaker>_enrollment`, one per speaker |
| Attribute `enrolled` | `sensor.<speaker>_enrolled_utterances` |
| Attribute `duration_s` | `speech_s` |
| `error: addon_unavailable` | `app_unavailable`, or `app_timeout` |
| `error: tee_not_installed` | `not_captured`, plus a repair |
| `error: no utterance yet` | `no_utterance` |
| Satellite gate: listening in the last 3 s | The exact pipeline task of the configured satellite |
| One STT entity, `stt.home_assistant_cloud` | Every STT entity, so the Voice PE's second assistant is heard too, whatever its engine |
| App hostname `local-aelita-voiceprint` | `<repository hash>-voxprint`, filled in by the config flow |
| `/config/.storage/aelita_voice_match` | `/config/.storage/voxprint` |

## Don't run both

Each one shadows the same method on `stt.home_assistant_cloud`. Installed together, their tees stack
in an order that the prototype re-wraps on every utterance, and removing Voxprint afterwards would
leave its tee inside the prototype's. Remove the prototype first.

## Steps

About 30 minutes with two Core restarts. Until step 7 the voice branch of `script.aelita_identify` is
false, so at the Voice PE everyone is `unknown` and private requests are offered to the phone. That is
the same failure mode as an empty voiceprint.

1. **Install the app.** Settings → Apps → App store → ⋮ → Repositories, add
   `https://github.com/ovflowd/voxprint`, install **Voxprint**, turn on *Watchdog*, start it. The log
   ends with `Voxprint app <version>, model wespeaker_resnet34_lm, self-test norm 1.0`. Leave the
   prototype's app running for now.
2. **Download the integration.** Marketplace → ⋮ → Custom repositories, add the same URL as an
   *Integration*, download **Voxprint**. Don't restart yet.
3. **Keep a copy of the voiceprint, then remove the prototype integration.** Over host SSH, copy
   `/mnt/data/supervisor/homeassistant/.storage/aelita_voice_match` into a folder only root can read.
   Then Settings → Devices & services → Aelita Voice Match → ⋮ → Delete. Its tee comes off at once,
   STT is stock, and its voiceprint file is deleted.
4. **Restart Home Assistant**, so it finds Voxprint.
5. **Add Voxprint.** Settings → Devices & services → Add integration → **Voxprint**. Keep the URL it
   suggests, and select only `assist_satellite.home_assistant_voice_pe`. In its options, keep the
   threshold at 0.50: the value the prototype ran with. Home Assistant 2026.11 puts the device's area
   in new entity IDs, so the sensor arrives as `sensor.bedroom_home_assistant_voice_pe_speaker`;
   rename it to `sensor.home_assistant_voice_pe_speaker`, like the Voice PE's other entities.
6. **Add yourself and bring the voiceprint over.** Add speaker, with your name, and your person entity
   as the person, so the sensor carries your user ID. Note the speaker's subentry ID (the integration's
   page, or the config entry's subentries). Then, over host SSH, one command per step:

   ```bash
   ha core stop
   ```

   ```bash
   C=/mnt/data/supervisor/homeassistant; umask 077
   jq '{version: 1, minor_version: 1, key: "voxprint", data: {model: .data.model, speakers: {"<subentry ID>": .data.samples}}}' \
     <the copy from step 3> > $C/.storage/voxprint.tmp && mv $C/.storage/voxprint.tmp $C/.storage/voxprint
   ```

   ```bash
   ha core start
   ```

   `sensor.<you>_enrolled_utterances` then shows the prototype's count. Both store the newest 150
   unit-length embeddings as base64 float16, and the copy's `model` must read `wespeaker_resnet34_lm`:
   any other model and Voxprint clears it with a repair. To enroll from scratch instead, turn on your
   Enrollment switch and give about 35 ordinary requests at the desk, alone.
7. **Point the identity script at the new sensor.** In `script.aelita_identify`, the `who` variable's
   voice branch reads:

   ```jinja
   {%- elif uid == '' and state_attr('sensor.aelita_voice_match', 'speaker') == 'claudio' and now() - states.sensor.aelita_voice_match.last_updated < timedelta(seconds=30) -%}claudio_voice
   ```

   Replace it with:

   ```jinja
   {%- elif uid == '' and state_attr('sensor.home_assistant_voice_pe_speaker', 'user_id') == '<the user ID of the claudio branch above>' and now() - states.sensor.home_assistant_voice_pe_speaker.last_updated < timedelta(seconds=30) -%}claudio_voice
   ```

   It compares the user ID rather than the name, so renaming the speaker can't break it, and a
   speaker without your person never matches. Update the script's description, which names the old
   sensor, too. The 30-second check still works: Voxprint moves `last_updated` on every utterance.
8. **Check what is exposed.** Settings → Voice assistants → Expose: the new speaker sensor and the
   enrollment switch must not be exposed to Assist or Google. The switch is a configuration entity
   and isn't by default; the sensor is an ordinary sensor, so check it. The Spook repair about the
   missing `sensor.aelita_voice_match` clears once the script no longer names it.
9. **Test it.**
   - Ask the Voice PE something private: answered, and the sensor says your name.
   - Wait 30 seconds and run `conversation.process` from a temporary automation: `unknown`.
   - Stop the Voxprint app and ask again: offered to the phone, with `error: app_unavailable`. Start it.
   - Have another voice ask: `unknown`. The 0.50 threshold was never calibrated in the room; calibrate
     now if you can ([enrollment.md](enrollment.md#calibrate)).
10. **Remove the prototype's files.** Uninstall the *Aelita Voiceprint* app. Over SSH, remove its local
    app folder (`/mnt/data/supervisor/apps/local/aelita_voiceprint` or `addons/local/…`, whichever
    exists) and `/mnt/data/supervisor/homeassistant/custom_components/aelita_voice_match`. Home Assistant
    stops listing it at its next restart. The prototype's repository stays as it is.

## Rolling back

Before step 10, the prototype's files are still there:

1. Delete the Voxprint integration (its voiceprints go with it) and stop its app.
2. Add **Aelita Voice Match** again, and put the copy from step 3 back as
   `.storage/aelita_voice_match` with Core stopped, or enroll with `switch.aelita_voice_enrolment`.
3. Put the old voice branch back into `script.aelita_identify`.
