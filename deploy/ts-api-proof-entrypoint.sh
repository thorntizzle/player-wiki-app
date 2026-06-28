#!/bin/sh
set -eu

export PLAYER_WIKI_ENV="${PLAYER_WIKI_ENV:-production}"
export PLAYER_WIKI_PORT="${PLAYER_WIKI_PORT:-8080}"
export PLAYER_WIKI_RUNTIME="${PLAYER_WIKI_RUNTIME:-typescript-image-proof}"
export PLAYER_WIKI_DB_PATH="${PLAYER_WIKI_DB_PATH:-/data/player_wiki.sqlite3}"
export PLAYER_WIKI_CAMPAIGNS_DIR="${PLAYER_WIKI_CAMPAIGNS_DIR:-/data/campaigns}"

export PORT="${PORT:-$PLAYER_WIKI_PORT}"
export CPW_DB_PATH="${CPW_DB_PATH:-$PLAYER_WIKI_DB_PATH}"
export CPW_CAMPAIGNS_DIR="${CPW_CAMPAIGNS_DIR:-$PLAYER_WIKI_CAMPAIGNS_DIR}"

if [ -z "${PLAYER_WIKI_BASE_URL:-}" ]; then
    if [ -n "${FLY_APP_NAME:-}" ]; then
        export PLAYER_WIKI_BASE_URL="https://${FLY_APP_NAME}.fly.dev"
    else
        export PLAYER_WIKI_BASE_URL="http://127.0.0.1:${PORT}"
    fi
fi

mkdir -p "$(dirname "$CPW_DB_PATH")"
mkdir -p "$CPW_CAMPAIGNS_DIR"

exec node /app/apps/api/dist/server.js
