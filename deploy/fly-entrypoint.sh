#!/bin/sh
set -eu

export PLAYER_WIKI_ENV="${PLAYER_WIKI_ENV:-production}"
export PLAYER_WIKI_HOST="${PLAYER_WIKI_HOST:-0.0.0.0}"
export PLAYER_WIKI_PORT="${PLAYER_WIKI_PORT:-8080}"
export PLAYER_WIKI_TRUST_PROXY="${PLAYER_WIKI_TRUST_PROXY:-true}"
export PLAYER_WIKI_PROXY_FIX_HOPS="${PLAYER_WIKI_PROXY_FIX_HOPS:-1}"
export PLAYER_WIKI_RELOAD_CONTENT="${PLAYER_WIKI_RELOAD_CONTENT:-false}"
export PLAYER_WIKI_DB_PATH="${PLAYER_WIKI_DB_PATH:-/data/player_wiki.sqlite3}"
export PLAYER_WIKI_CAMPAIGNS_DIR="${PLAYER_WIKI_CAMPAIGNS_DIR:-/data/campaigns}"

if [ -z "${PLAYER_WIKI_BASE_URL:-}" ] && [ -n "${FLY_APP_NAME:-}" ]; then
    export PLAYER_WIKI_BASE_URL="https://${FLY_APP_NAME}.fly.dev"
fi

mkdir -p "$(dirname "$PLAYER_WIKI_DB_PATH")"
mkdir -p "$PLAYER_WIKI_CAMPAIGNS_DIR"

python manage.py init-db

exec gunicorn \
    --bind "0.0.0.0:${PLAYER_WIKI_PORT}" \
    --workers "${GUNICORN_WORKERS:-1}" \
    --threads "${GUNICORN_THREADS:-4}" \
    --timeout "${GUNICORN_TIMEOUT:-60}" \
    --access-logfile - \
    --error-logfile - \
    wsgi:app
