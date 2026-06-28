FROM node:22-slim AS frontend-build

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY frontend/ ./
RUN npm run build

FROM node:22-slim AS ts-api-build

WORKDIR /app/apps/api

COPY apps/api/package.json apps/api/package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY apps/api/tsconfig.json ./tsconfig.json
COPY apps/api/src ./src
RUN npm run build \
    && npm prune --omit=dev

FROM node:22-slim AS ts-api-runtime-proof

ARG PLAYER_WIKI_BUILD_ID=unknown
ARG PLAYER_WIKI_GIT_SHA=unknown
ARG PLAYER_WIKI_GIT_DIRTY=false

ENV NODE_ENV=production \
    PLAYER_WIKI_ENV=production \
    PLAYER_WIKI_PORT=8080 \
    PLAYER_WIKI_RUNTIME=typescript-image-proof \
    PLAYER_WIKI_CAMPAIGNS_DIR=/data/campaigns \
    PLAYER_WIKI_DB_PATH=/data/player_wiki.sqlite3 \
    PLAYER_WIKI_BUILD_ID=${PLAYER_WIKI_BUILD_ID} \
    PLAYER_WIKI_GIT_DIRTY=${PLAYER_WIKI_GIT_DIRTY} \
    PLAYER_WIKI_GIT_SHA=${PLAYER_WIKI_GIT_SHA}

WORKDIR /app

COPY VERSION ./VERSION
COPY --from=ts-api-build /app/apps/api/package.json ./apps/api/package.json
COPY --from=ts-api-build /app/apps/api/package-lock.json ./apps/api/package-lock.json
COPY --from=ts-api-build /app/apps/api/node_modules ./apps/api/node_modules
COPY --from=ts-api-build /app/apps/api/dist ./apps/api/dist
COPY deploy/ts-api-proof-entrypoint.sh ./deploy/ts-api-proof-entrypoint.sh

RUN sed -i 's/\r$//' /app/deploy/ts-api-proof-entrypoint.sh \
    && chmod +x /app/deploy/ts-api-proof-entrypoint.sh

EXPOSE 8080

CMD ["/app/deploy/ts-api-proof-entrypoint.sh"]

FROM python:3.12-slim

ARG PLAYER_WIKI_BUILD_ID=unknown
ARG PLAYER_WIKI_GIT_SHA=unknown
ARG PLAYER_WIKI_GIT_DIRTY=false

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt requirements-prod.txt ./
RUN pip install --no-cache-dir -r requirements-prod.txt

COPY . .
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

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
