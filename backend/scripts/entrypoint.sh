#!/usr/bin/env bash
# Container entrypoint: migrate, seed, then serve.
#
# Migrations run before the app starts so a rolling deploy never has a process talking
# to a schema it does not expect. Seeding is idempotent, so re-running is safe.
set -euo pipefail

echo "Running database migrations…"
alembic upgrade head

if [ "${SEED_ON_START:-true}" = "true" ]; then
  echo "Seeding the reference corpus…"
  python -m app.workers.seed_cli
fi

echo "Starting the API…"
exec "$@"
