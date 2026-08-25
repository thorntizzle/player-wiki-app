FROM python:3.12.12-slim-bookworm@sha256:593bd06efe90efa80dc4eee3948be7c0fde4134606dd40d8dd8dbcade98e669c

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /workspace

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-dev.lock /tmp/requirements-dev.lock
RUN python -m pip install --no-cache-dir --require-hashes -r /tmp/requirements-dev.lock
RUN python -m playwright install --with-deps chromium

COPY . /workspace
RUN mkdir -p /workspace/.git /workspace/.local
