#!/usr/bin/env bash
# Start a backend for the end-to-end suite: a throwaway SQLite database, the
# deterministic offline AI provider, and rate limits raised so the tests are not
# throttled. Nothing here touches a development or production database.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE="${E2E_STATE_DIR:-/tmp/starcode-e2e}"
PORT="${E2E_API_PORT:-8100}"

rm -rf "$STATE"
mkdir -p "$STATE/uploads"

cd "$ROOT/backend"

export DATABASE_URL="sqlite:///$STATE/e2e.db"
export ENVIRONMENT=development
export AI_PROVIDER=offline
export UPLOAD_DIR="$STATE/uploads"
export SECRET_KEY="e2e-only-secret-not-used-anywhere-real"
export CORS_ORIGINS="http://127.0.0.1:${E2E_WEB_PORT:-3100},http://localhost:${E2E_WEB_PORT:-3100}"
export RATE_LIMIT_ANONYMOUS_PER_HOUR=100000
export RATE_LIMIT_USER_PER_HOUR=100000
export LOG_LEVEL=WARNING

python3 -c "
from app.db.session import create_all, session_scope
from app.knowledge.seed import seed_all
create_all()
with session_scope() as db:
    seed_all(db)
print('e2e database ready')
"

exec python3 -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" --log-level warning
