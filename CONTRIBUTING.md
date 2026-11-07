# Contributing

Thanks for helping. Voxprint is small on purpose, and people use it to keep private things private,
so a change should be small too: one change per pull request, and a behavior change comes with a test.

## Setup

The integration and the app are two uv projects: the repository root (Home Assistant and its test
package) and `app/` (onnxruntime and the model's dependencies).

```sh
git clone https://github.com/ovflowd/voxprint.git
cd voxprint
uv sync
(cd app && uv sync)
python3 -I app/fetch_model.py models
uv run pytest
(cd app && uv run pytest)
uv run ruff check .
uv run ruff format --check .
```

The integration's tests run the real Assist pipeline with a fake STT engine, fake satellites and a
fake app. `tests/test_end_to_end.py` starts the real app with the real model and talks to it with
synthetic voices; it skips itself without `app/.venv` or the model. The app's model tests skip too.
To try the image: `docker build -t voxprint-app app`.

## Style

- Ruff formats and lints, with the settings in `pyproject.toml` (120 columns). CI checks both.
- A comment says why, not what. Do not restate the code.
- Never nest `await` inside another expression: give the awaited value its own line.
- Follow the current Home Assistant patterns: `runtime_data`, translation keys, no `_attr_name` for
  entities with a device, repairs for problems the user has to act on.
- Commit messages are an imperative sentence with a type, as in `fix: drop a score that arrives
  late`, and the body says why.

## What must not change by accident

- **Fail closed.** No speaker is named unless this utterance's own score cleared the threshold. A
  change that names one in any other case needs a test that shows why it is safe.
- **STT is untouched.** The tee passes every chunk, result and exception through unchanged, and never
  delays the engine. `tests/test_tee.py` holds the rules.
- **No audio leaves RAM**, and only embeddings are stored. Never add a debug option that saves audio.
- **The model's numbers.** `app/tests/test_model.py` compares an embedding with a recorded reference.
  If a dependency update moves it, every enrolled voiceprint would score differently: that is a
  breaking change, not a test to update.

## Voices in this repository

Never commit a recording of anyone's voice, a voiceprint, an embedding of a real voice, or a
`.storage` file. Tests use synthetic voices (`tests/synth.py`, `app/tests/synth.py`), and CI checks
that no audio file is tracked. Attach recordings to an issue only if the person in them agreed, and
prefer numbers (scores, `speech_s`) to audio.

## Artwork

The icons are drawn in `assets/` and rendered with `rsvg-convert`: `icon.svg` at 256 and 512 px into
`custom_components/voxprint/brand/`, at 128 px into `app/icon.png`, and `logo.svg` into `app/logo.png`.

## Releasing

- **Integration:** set `version` in `custom_components/voxprint/manifest.json` and `pyproject.toml`,
  then publish a GitHub release whose tag is that version, such as `0.2.0`.
- **App:** set `version` in `app/config.yaml`, `app/pyproject.toml` and `server.__version__`, and add
  it to `app/CHANGELOG.md`. The App workflow publishes the images when that lands on `main`; it never
  overwrites a published version. Home Assistant offers the update from `config.yaml`.

## AI assistants

If you used an AI assistant for a change, say so in the pull request. You remain responsible for it,
and for having read it.

## License of contributions

By contributing, you agree that your work is licensed under the [MIT license](LICENSE). This
project follows a [code of conduct](CODE_OF_CONDUCT.md).

## Reporting a problem

Questions and ideas are welcome as issues too. For a bug, include the integration's and the app's
versions, your Home Assistant version and installation type, the satellite and the STT engine, and
the speaker sensor's attributes. Download the diagnostics from the integration's page: they leave
out names, persons and addresses. For a security problem, see [SECURITY.md](SECURITY.md).
