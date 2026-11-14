# Debian rather than Home Assistant's Alpine base images: onnxruntime ships glibc wheels only.
FROM python:3.15-slim-trixie@sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928 AS build

COPY --from=ghcr.io/astral-sh/uv:0.13.7@sha256:96f40d3904aad8d0bd010539001d36c8e2188b981e1334471a90c4a1d93bb490 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv UV_PYTHON_DOWNLOADS=never

COPY fetch_model.py /build/
RUN python3 -I /build/fetch_model.py /models

COPY pyproject.toml uv.lock /build/
RUN cd /build && uv sync --locked --no-dev --no-install-project

FROM python:3.15-slim-trixie@sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MODEL_DIR=/models ORT_DISABLE_TELEMETRY=1

COPY --from=build /models /models
COPY --from=build /opt/venv /opt/venv
COPY server.py /app/server.py

LABEL \
    org.opencontainers.image.title="Voxprint" \
    org.opencontainers.image.description="Turns one utterance into a speaker embedding for the Voxprint integration, keeping nothing" \
    org.opencontainers.image.source="https://github.com/ovflowd/voxprint" \
    org.opencontainers.image.licenses="MIT"

# Runs as root: the Supervisor writes /data/options.json with mode 0600, and the app writes nothing.
EXPOSE 10340
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
    CMD python3 -I -c "import os, urllib.request as r; r.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT', '10340'), timeout=3)"
CMD ["/opt/venv/bin/python", "-I", "/app/server.py"]
