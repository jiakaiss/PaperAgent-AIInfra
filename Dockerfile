# syntax=docker/dockerfile:1.7
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Optional build-time pip mirror (passed via --build-arg PIP_INDEX_URL=... and
# PIP_TRUSTED_HOST=... at `docker compose build`). Defaults to the public PyPI;
# set to e.g. http://mirrors.tencentyun.com/pypi/simple inside Tencent Cloud
# to avoid pypi.org timeouts.
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOST=""
ENV PIP_INDEX_URL=$PIP_INDEX_URL \
    PIP_TRUSTED_HOST=$PIP_TRUSTED_HOST

# ── Stage 1: install dependencies ─────────────────────────────────────────────
# Copy only the dependency declaration + a stub src/ tree, then `pip install .`
# to fetch every third-party dep declared in pyproject.toml. The stub keeps
# hatchling happy (`packages = ["src/paper_agent"]` only needs the directory to
# exist). This layer is only invalidated when pyproject.toml or README.md
# changes — NOT when application code changes — so iterating on src/ skips this.
COPY pyproject.toml README.md ./
RUN mkdir -p src/paper_agent \
    && touch src/paper_agent/__init__.py
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip \
    && pip install hatchling \
    && pip install .

# ── Stage 2: install the real application code ────────────────────────────────
# Replace the stub with real source and reinstall the package WITHOUT deps —
# this just copies the package files into site-packages, ~1s, no network.
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-deps --force-reinstall --no-build-isolation .

RUN mkdir -p /app/data /app/logs /app/backups

EXPOSE 8000

CMD ["paper-agent", "web", "--host", "0.0.0.0", "--port", "8000", "--config", "/app/config.yaml"]
