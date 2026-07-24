#!/bin/sh
set -eu

if [ -z "${SAKURAPLAYER_DATABASE_URL:-}" ]; then
  database_url=$(
    python - "${POSTGRES_PASSWORD_FILE}" "${POSTGRES_USER}" "${POSTGRES_DB}" <<'PY'
from pathlib import Path
import sys
from urllib.parse import quote

password = quote(Path(sys.argv[1]).read_text(encoding="utf-8").strip(), safe="")
username = quote(sys.argv[2], safe="")
database = quote(sys.argv[3], safe="")
print(f"postgresql+psycopg://{username}:{password}@postgres:5432/{database}")
PY
  )
  export SAKURAPLAYER_DATABASE_URL="${database_url}"
  unset database_url
fi

exec "$@"
