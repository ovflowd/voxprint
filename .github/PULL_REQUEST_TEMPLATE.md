## What changes, and why

## How I tested it

- [ ] `uv run pytest` and `(cd app && uv run pytest)` pass, with the model fetched
- [ ] `uv run ruff check .` and `uv run ruff format --check .` are clean
- [ ] A behavior change has a test and a line in the docs
- [ ] It still fails closed, and STT still passes through unchanged
- [ ] No recordings, voiceprints, embeddings of real voices or `.storage` files
