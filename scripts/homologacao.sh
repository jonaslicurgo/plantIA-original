#!/bin/sh
# Use um volume novo e credenciais exclusivas de homologação.
set -eu
: "${PLANET_STAGING_DATA_DIR:?Informe um diretório exclusivo e persistente de homologação}"
case "$PLANET_STAGING_DATA_DIR" in
  /*) ;;
  *) echo 'O diretório de homologação precisa ser absoluto.' >&2; exit 2 ;;
esac
export PLANET_DATA_DIR="$PLANET_STAGING_DATA_DIR"
export GEMINI_API_KEY="${PLANET_STAGING_GEMINI_API_KEY:-}"
export GEMINI_MODEL="${PLANET_STAGING_GEMINI_MODEL:-gemini-3.1-flash-lite}"
export PLANET_PUBLIC_ORIGIN="${PLANET_STAGING_PUBLIC_ORIGIN:-http://127.0.0.1:8081}"
export PLANET_SMTP_HOST="${PLANET_STAGING_SMTP_HOST:-}"
export PLANET_SMTP_PORT="${PLANET_STAGING_SMTP_PORT:-465}"
export PLANET_SMTP_FROM="${PLANET_STAGING_SMTP_FROM:-}"
export PLANET_SMTP_USER="${PLANET_STAGING_SMTP_USER:-}"
export PLANET_SMTP_PASSWORD="${PLANET_STAGING_SMTP_PASSWORD:-}"
export PLANET_INSECURE_LOCAL_HTTP="${PLANET_STAGING_INSECURE_LOCAL_HTTP:-0}"
export PYTHON_DOTENV_DISABLED=1
umask 077
exec python -m uvicorn main:app --host "${PLANET_STAGING_HOST:-127.0.0.1}" --port "${PLANET_STAGING_PORT:-8081}"
