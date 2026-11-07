# Accuracy

What to expect, from measurements on recordings with the app's own code. None of this went through a
satellite, which is why you should [calibrate](enrollment.md#calibrate) at yours.

## How it was measured

- **The enrolled voice:** four English conference talks by one man (2018 to 2025), cut into windows of
  1, 2, 3 and 5 seconds. For each talk, its first 3 minutes (36 × 5 s) were enrolled; that voiceprint
  was tested on the rest of the same talk and on the other three talks.
- **Other voices:** 18 men from LibriSpeech (read speech, 2.4 hours), the same windows, scored against
  every voiceprint.

## At the default threshold, 0.5

| Speech in the utterance | The enrolled man, same recording | The same man, other recordings | Other men |
|---|---|---|---|
| 0.7 s | 63 % | 18 % | 0 of 31,036 |
| 1.4 s | 95 % | 51 % | 1 of 15,136 |
| 2.2 s | 99 % | 69 % | 0 of 9,768 |
| 3.8 s | 100 % | 82 % | 0 of 6,196 |

At a Home Assistant Voice PE, one man's enrollment utterances scored 0.51 to 0.85 for normal sentences
and about 0.45 for one-second commands.

## What it means, and what it can't show

- **One of the 18 men gets through.** He passes at 0.5 about once in 900 tries at 1.4 s of speech, and
  reached 0.521. Every false accept in the table is his.
- **The threshold was chosen on these same 18 men**, so the "Other men" column is in-sample and
  flatters it.
- **The microphone matters as much as the voice:** 95 to 100 % on the recording the voiceprint came
  from, 51 to 82 % on another one. Enroll at the satellite the person uses.
- **Under a second of speech is unreliable.** Short commands such as "lights off" are often turned
  away; ask for something private in a full sentence.
- **The other men were recorded on other microphones.** Someone speaking at your satellite shares its
  microphone and room, and will score higher than they did here.
- **Women, children and other languages weren't measured,** and 18 men can't rule out a voice closer
  to an enrolled one.
- **A recording passes.** Anyone with a recording of an enrolled person can play it to the satellite.
