FROM python:3.12.12-slim-bookworm@sha256:593bd06efe90efa80dc4eee3948be7c0fde4134606dd40d8dd8dbcade98e669c

ARG PLAYER_WIKI_BUILD_ID=unknown
ARG PLAYER_WIKI_GIT_SHA=unknown
ARG PLAYER_WIKI_GIT_DIRTY=false

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements-prod.lock ./
RUN python -m pip install --no-cache-dir --require-hashes -r requirements-prod.lock

COPY . .

RUN sed -i 's/\r$//' /app/deploy/fly-entrypoint.sh \
    && chmod +x /app/deploy/fly-entrypoint.sh

ENV PLAYER_WIKI_ENV=production \
    PLAYER_WIKI_HOST=0.0.0.0 \
    PLAYER_WIKI_PORT=8080 \
    PLAYER_WIKI_TRUST_PROXY=true \
    PLAYER_WIKI_PROXY_FIX_HOPS=1 \
    PLAYER_WIKI_RELOAD_CONTENT=false \
    PLAYER_WIKI_RUNTIME=fly \
    PLAYER_WIKI_CAMPAIGNS_DIR=/data/campaigns \
    PLAYER_WIKI_BUILD_ID=${PLAYER_WIKI_BUILD_ID} \
    PLAYER_WIKI_GIT_DIRTY=${PLAYER_WIKI_GIT_DIRTY} \
    PLAYER_WIKI_GIT_SHA=${PLAYER_WIKI_GIT_SHA} \
    PLAYER_WIKI_DB_PATH=/data/player_wiki.sqlite3

EXPOSE 8080

CMD ["/app/deploy/fly-entrypoint.sh"]
