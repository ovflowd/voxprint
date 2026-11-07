# Voxprint

This app turns one utterance into a speaker embedding with WeSpeaker ResNet34-LM, for the
[Voxprint integration](https://github.com/ovflowd/voxprint). The integration sends it the audio of
each utterance from your satellites and compares the embeddings with the voiceprints it keeps.

## Setup

1. Start the app, with *Watchdog* on. Its log should end with
   `Voxprint app 0.1.0, model wespeaker_resnet34_lm, self-test norm 1.0`.
2. Install the Voxprint integration from the Marketplace (HACS) and restart Home Assistant.
3. Add the integration under Settings → Devices & services. It finds this app's address by itself:
   `http://<hostname>:10340`, with the hostname shown on this app's info page.

The integration's [documentation](https://github.com/ovflowd/voxprint#readme) covers enrolling
speakers and setting the threshold.

## Options

| Option | |
|---|---|
| `log_level` | `info` by default. At `debug` the app logs one line per utterance: its length, the seconds of speech and how long the model took. It never logs audio or results |

## Privacy

- Audio lives in RAM for one request and is never written anywhere. The app keeps no state, so its
  backup is empty.
- It has no host ports and no access to Home Assistant's or the Supervisor's API. Home Assistant
  reaches it on the internal network.
- The model is downloaded when the image is built and checked against a pinned SHA-256; the app needs
  no internet afterwards.

## API

| | |
|---|---|
| `POST /v1/embed` | Raw PCM, 16-bit little-endian, 16 kHz, mono, at most 15 s. Returns the embedding, the model, and the seconds of audio and of speech; `too_short` when there is too little speech. At most 6 s of speech is used. One utterance is embedded at a time; with 5 requests in the app, more get `503` |
| `GET /health` | `ok`, the API version, the model and the app's version |

## Model

WeSpeaker ResNet34-LM trained on VoxCeleb, as exported to ONNX by sherpa-onnx. It is licensed
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), following VoxCeleb's license;
[NOTICE](https://github.com/ovflowd/voxprint/blob/main/NOTICE) has the attribution. The app uses it
unmodified.
