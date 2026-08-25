# Installation

Two paths: Docker (everything, one command) or local (more control, useful for
development). Both give a working platform with no AI credentials.

---

## Requirements

| | Docker path | Local path |
| --- | --- | --- |
| Docker Engine | 24+ with Compose v2 | — |
| Python | — | 3.11 or 3.12 |
| Node.js | — | 20+ (22 recommended) |
| PostgreSQL | — | 16 with pgvector (optional — SQLite works) |
| Redis | — | 7 (optional) |
| Tesseract | — | optional, for OCR |

Roughly 2 GB of disk for images and dependencies.

---

## Docker

```bash
git clone <repository> starcode
cd starcode
cp .env.example .env
docker compose up --build
```

That brings up Postgres with pgvector, Redis, the API, a background worker and the web
app. Migrations and corpus seeding run automatically on start.

| Service | URL |
| --- | --- |
| Web app | http://localhost:3000 |
| API | http://localhost:8000 |
| Interactive API docs | http://localhost:8000/docs |
| Health | http://localhost:8000/api/v1/health |

Verify it is working:

```bash
curl -s localhost:8000/api/v1/health | python3 -m json.tool
```

`"status": "ok"` and a non-zero `corpus.indexed_chunks` means everything is up.

### Enabling the language model

Optional. Without it, extraction, calendars and astronomy work fully and the interpretive
sections report themselves as unavailable.

```bash
# in .env
ANTHROPIC_API_KEY=sk-ant-...
```

```bash
docker compose up -d --force-recreate api worker
```

### Common Docker problems

**Port already in use.** Change it in `.env` (`API_PORT`, `WEB_PORT`, `POSTGRES_PORT`)
and re-run.

**The web app cannot reach the API.** `NEXT_PUBLIC_API_URL` is compiled into the browser
bundle at build time, so changing it requires a rebuild, not just a restart:

```bash
docker compose build web && docker compose up -d web
```

It must also match the API's `CORS_ORIGINS` and the frontend middleware's CSP
`connect-src`. A mismatch shows up in the browser console as a refused connection rather
than a server error. `localhost` and `127.0.0.1` are *different origins* for this purpose
— pick one and use it everywhere.

**Postgres will not start.** Usually a volume left over from a different Postgres major
version. `docker compose down -v` clears it, and deletes the data with it.

---

## Local installation

### Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

The simplest working configuration needs no services at all:

```bash
export DATABASE_URL="sqlite:///./starcode.db"
export ENVIRONMENT=development
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"

alembic upgrade head
python -m app.workers.seed_cli
uvicorn app.main:app --reload --port 8000
```

SQLite is genuinely supported — the whole test suite runs on it. Semantic search falls
back to an in-process cosine scan instead of pgvector, which is correct but slower, and
fine at seed-corpus scale.

#### With PostgreSQL

```bash
createdb starcode
psql starcode -c "CREATE EXTENSION IF NOT EXISTS vector;"
export DATABASE_URL="postgresql+psycopg://user:password@localhost:5432/starcode"
alembic upgrade head
python -m app.workers.seed_cli
```

The `vector` extension needs [pgvector](https://github.com/pgvector/pgvector) installed;
the `pgvector/pgvector:pg16` image has it built in. The migration creates the extension
itself if the connecting role has permission.

#### Optional: OCR

Without these, image and scanned-PDF uploads are rejected with a message saying OCR is
unavailable. Text, digital PDFs and Word documents are unaffected.

```bash
# Debian/Ubuntu — the language packs matter for non-Latin manuscripts
sudo apt-get install tesseract-ocr tesseract-ocr-eng tesseract-ocr-grc \
                     tesseract-ocr-heb tesseract-ocr-ara tesseract-ocr-lat \
                     poppler-utils

# macOS
brew install tesseract tesseract-lang poppler
```

Then list the languages you want:

```bash
export OCR_LANGUAGES="eng,grc,heb"
```

#### Optional: Redis

Without Redis, rate limiting falls back to in-process counters. That is correct for a
single worker and degrades to per-worker limits with several — not to *no* limits. The
health endpoint reports which backend is active.

```bash
export REDIS_URL="redis://localhost:6379/0"
```

### Frontend

```bash
cd frontend
npm install
export NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev
```

Open http://localhost:3000.

For a production build locally:

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run build
npm start
```

### Background worker (optional)

The API runs jobs on a worker thread, which is right for development. To move that work
off the request path:

```bash
cd backend && python -m app.workers.runner
```

Jobs live in the database, so the two approaches interoperate and a job interrupted by a
restart is picked up rather than lost.

---

## Verifying the installation

```bash
cd backend && pytest -q              # expect: 325 passed
cd frontend && npm test              # expect: 29 passed
cd frontend && npm run typecheck     # expect: no output
```

End to end, against a real backend:

```bash
./scripts/e2e-backend.sh &           # from the repository root
cd frontend
NEXT_PUBLIC_API_URL=http://127.0.0.1:8100 npm run build
npx playwright install --with-deps chromium
npx playwright test --project=chromium
```

A quick manual check that the whole pipeline works:

```bash
curl -s -X POST localhost:8000/api/v1/analyses \
  -H 'Content-Type: application/json' \
  -d '{"text":"And the moon became as blood. In 587 BC Jerusalem fell."}'
```

You will get an `id` and an `anonymous_token`. Poll the status, then fetch the report
with that token in an `X-Analysis-Token` header. See [API.md](API.md).

---

## Configuration

Everything is environment-driven. `.env.example` is the annotated list; the essentials:

| Variable | Default | Notes |
| --- | --- | --- |
| `ENVIRONMENT` | `development` | `production` enables strict startup checks |
| `SECRET_KEY` | dev sentinel | **The app refuses to boot in production with the default.** |
| `DATABASE_URL` | local Postgres | `sqlite:///./starcode.db` also works |
| `ANTHROPIC_API_KEY` | *(empty)* | Optional; without it the offline engine runs |
| `AI_PROVIDER` | `auto` | `auto`, `anthropic` or `offline` |
| `CORS_ORIGINS` | `http://localhost:3000` | Must match where the web app is served |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Compiled into the browser bundle |
| `MAX_UPLOAD_BYTES` | 25 MB | |
| `RATE_LIMIT_ANONYMOUS_PER_HOUR` | 10 | Raised substantially for signed-in users |
| `OCR_LANGUAGES` | `eng` | Comma-separated Tesseract codes |

Generate a real secret with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

---

## Upgrading

```bash
git pull
cd backend && pip install -e ".[dev]" && alembic upgrade head && python -m app.workers.seed_cli
cd ../frontend && npm install && npm run build
```

Seeding is idempotent — existing rows are updated rather than duplicated — so it is safe
on every deploy.

---

## Uninstalling

```bash
docker compose down -v   # -v also deletes the database and uploaded files
```
