# Enrolling speakers and calibrating

## Add a speaker

On the Voxprint integration's page, choose **Add speaker** and give a name. Optionally pick the
person they are: the speaker sensors then also show that person and their user ID, so a script can
treat a recognized voice like that user logged in. Each speaker gets a device with an **Enrollment**
switch, an **Enrolled utterances** count and a **Reset voiceprint** button.

## Enroll: about 3 minutes of normal talk

1. Have the speaker alone in the room, with the TV and music off. Anyone else who talks while the
   switch is on can end up in their voiceprint.
2. Turn on their **Enrollment** switch. It turns itself off after 30 minutes, and only one speaker
   enrolls at a time. It listens to one satellite: the first that hears the speaker after the switch
   goes on.
3. About 35 times: the wake word, then one or two ordinary sentences, about five seconds each. Ask real
   things, give commands, at the distance and volume they normally use. Say a few from wherever else
   they talk to that satellite. The microphone and the room change the voice, so enroll some at each
   satellite they use: turn the switch off and on again before moving to the next one.
4. **Enrolled utterances** goes up by one each time. Utterances with under half a second of speech are
   skipped, and from the second one on, so is anything that sounds nothing like the voiceprint so far.
5. Turn the switch off.

At most 6 seconds of speech per utterance are used, so 35 utterances are about 3 minutes. The
voiceprint keeps the newest 150; enrolling again later adds to it.

The first utterance is taken as it is, since there is nothing to compare it with, and it picks the
satellite the session listens to. If someone else spoke first, at that satellite or at another one,
**Enrolled utterances** stays at 1 while the speaker keeps talking: press **Reset voiceprint** and
start again, with nobody near any satellite.

## Calibrate

The default threshold, 0.5, comes from recordings ([accuracy.md](accuracy.md)), not from your
satellites. A satellite's microphone and your room move every score, so set the threshold from your
own:

1. **Watch the scores.** The speaker sensor's `scores` attribute has every enrolled speaker's score
   for each utterance. To see them over time, add a template sensor per speaker under Settings →
   Devices & services → Helpers, with a state such as
   `{{ state_attr('sensor.kitchen_satellite_speaker', 'scores').get('Alice') }}`. The history panel
   then plots them.
2. **The enrolled speakers.** With every enrollment switch off, have each one give 20 ordinary
   requests of mixed length, short ones too. Note their own scores.
3. **Other voices.** Have people who aren't enrolled talk to the satellite, and play other voices from
   a speaker at talking distance: podcasts, audiobooks, other people's recordings. Note the highest
   score any of them got for each enrolled speaker. Look hardest at voices like an enrolled speaker's.
4. **Set the threshold** to the highest score any other voice reached, plus 0.05, and never below 0.5.
   Set it in Voxprint's options.
5. **Check it.** Count each enrolled speaker's 20 requests at or above it.
   - 16 or more: done.
   - Fewer: enroll 10 to 15 more utterances and repeat step 2. Don't lower the threshold below the line
     from step 4. A request under it only means the speaker isn't recognized for that one.
   - If another voice scored at or above an enrolled speaker's median, Voxprint can't tell them apart
     in this room. Don't rely on it for anything private.

With several enrolled speakers, `error: ambiguous` means two of them both cleared the threshold
within 0.05 of each other. Enroll both with more utterances; if it keeps happening, they sound too
alike to tell apart.

Calibrate again after moving a satellite, changing its microphone settings, or enrolling more.
