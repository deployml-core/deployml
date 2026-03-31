#!/usr/bin/env sh
set -e

# Map Cloud Run's PORT → Grafana's expected var
export GF_SERVER_HTTP_PORT="${PORT:-${GF_SERVER_HTTP_PORT:-8080}}"

echo "Starting Grafana on port ${GF_SERVER_HTTP_PORT}..."
[ -n "${GF_DATABASE_URL:-}" ] && echo "Using database: ${GF_DATABASE_URL}"

exec /run.sh
