# Security policy

## Reporting a vulnerability

Please report a vulnerability privately, through
[GitHub's private vulnerability reporting](https://github.com/ovflowd/voxprint/security/advisories/new),
and not in a public issue. Include what you found, how to reproduce it and what it affects. You will
get an answer within a week.

If that page does not open, open an issue that only says you have a security problem to report, and
without any detail, so that a way to talk privately can be arranged.

## Scope

Voxprint decides whether a voice belongs to an enrolled person, and people use that to keep private
things private. In scope are problems in this repository's code, for example a way to make Voxprint:

- name a speaker for an utterance that wasn't scored, scored too late, or scored below the threshold;
- capture audio from anything other than a configured satellite, keep audio after scoring, or write
  it anywhere;
- store anything but embeddings, store them where other users can read them, or keep them after a
  speaker or the integration is removed;
- let someone enroll, or add audio to another person's voiceprint, without the enrollment switch;
- change, delay or break speech-to-text;
- put names, persons, user IDs, addresses or embeddings into diagnostics or logs;
- crash or exhaust the app with a request.

A voice that sounds like an enrolled speaker and passes is a limit of speaker recognition, not a
vulnerability: [docs/accuracy.md](docs/accuracy.md) says what to expect. A recording of an enrolled
speaker played back to a satellite will pass too: Voxprint has no liveness detection.

Problems in Home Assistant, its Assist pipeline, the STT engine, onnxruntime or the WeSpeaker model
belong to those projects.

## What Voxprint touches

See [Privacy](docs/how-it-works.md#privacy): what it captures, sends, stores and never writes.

## Supported versions

Only the latest release.
