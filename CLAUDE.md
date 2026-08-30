# CLAUDE.md

Guidance for Claude Code and other AI assistants working in this repository.

Read this first, then [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for *why* the system
is shaped the way it is, and [`docs/DEVELOPER.md`](docs/DEVELOPER.md) for extension
recipes (adding a calendar, an agent, corpus data, an endpoint).

---

## What this project is

**Starcode** analyses ancient texts, manuscripts, prophecies and historical documents and
returns a structured report that separates what is *established* from what is
*interpreted* from what is *conjectured*.

A Next.js 15 frontend talks REST to a FastAPI backend. The backend runs an eight-agent
pipeline over the submitted text, backed by two pure deterministic engines (astronomy and
calendars), a curated corpus with vector retrieval, and PostgreSQL + pgvector.

### The one rule that governs every change

> **Speculation is never presented as established fact.**

This is enforced structurally, not by wording. Every statement is a **claim** with a
mandatory `claim_type`, and the rules for each type are checked in code
(`backend/app/agents/contracts.py`) on the way to the database:

| Claim type | Requirement enforced by the contract |
| --- | --- |
| `source_text` | Must carry the verbatim quotation |
| `verified_history` | ≥1 citation, or it is downgraded |
| `astronomical_calculation` | Must name its engine |
| `astronomical_dating_candidate` | Must name its engine **and** carry `matched_criteria`/`unmatched_criteria`; confidence capped like `ai_hypothesis` |
| `scholarly_interpretation` | ≥1 citation, or it is downgraded |
| `textual_analysis` | — |
| `traditional_interpretation` | Reported, never endorsed |
| `ai_hypothesis` | Confidence capped at `AI_HYPOTHESIS_CONFIDENCE_CAP` (0.55); may not assert a future event as settled |
| `uncertain` | — |

A violating claim is **downgraded visibly** by `coerce_claim()` and the downgrade is
recorded in `payload.contract_adjustments`. It is never silently dropped (loses
information) and never silently promoted (the exact failure this product exists to
prevent).

`backend/tests/test_contracts.py` is the specification. Read it before touching anything
in `agents/`.

---

## Commands

All backend commands run from `backend/`, all frontend commands from `frontend/`.

### Setup

```bash
# Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
export DATABASE_URL="sqlite:///./dev.db"
export ENVIRONMENT=development
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
alembic upgrade head
python -m app.workers.seed_cli      # idempotent corpus seed
uvicorn app.main:app --reload

# Frontend, in another terminal
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

Or the whole stack: `cp .env.example .env && docker compose up --build` → http://localhost:3000.

SQLite and the offline provider are fully supported for development. **No PostgreSQL, no
Redis and no API key are needed for almost any work.**

### The inner loop

```bash
# backend/
pytest -q                          # 435 tests, ~50s, no services needed
pytest tests/test_astronomy.py -q  # one file
pytest -k "eclipse" -q             # by name
ruff check app tests scripts --fix
ruff format app tests scripts      # CI runs `ruff format --check`
mypy app                           # advisory only; CI does not block on it

# frontend/
npm test                           # vitest unit tests
npm run typecheck
npm run lint
npm run build
```

### End-to-end and accessibility

```bash
./scripts/e2e-backend.sh &         # from the repo root: throwaway SQLite on :8100
cd frontend
NEXT_PUBLIC_API_URL=http://127.0.0.1:8100 NEXT_PUBLIC_ALLOW_LOCALHOST=true npm run build
npx playwright test --project=chromium
```

Playwright starts the web server itself on `:3100` (`next start`), so the build must run
first. `scripts/e2e-backend.sh` wipes `/tmp/starcode-e2e` and touches nothing else.

`npm run test:a11y` runs the accessibility suite alone (`tests/e2e/a11y.spec.ts`, 20
tests). Playwright's positional argument is a regex matched against the path *as the
runner resolves it*, so a filter that omits the `e2e/` segment silently selects nothing
rather than erroring usefully — check `--list` before trusting a narrowed run.

### Database changes

```bash
# edit backend/app/db/models/*.py
alembic revision --autogenerate -m "add thing table"
# READ the generated file — autogenerate is a first draft, not an answer
alembic upgrade head
```

Check every generated migration for:
- Custom types rendering as `app.db.types.JSONBType()` / `VectorType()`, with the module
  imported in the migration file.
- PostgreSQL-specific operations guarded by
  `if op.get_bind().dialect.name == "postgresql":`
- A `downgrade()` that genuinely reverses `upgrade()` — CI runs the round trip.

CI also runs `alembic check`, which fails if the models and the migrations disagree.

---

## Repository layout

```
backend/
  app/
    agents/
      contracts.py      the epistemic contract — the most important file in the repo
      orchestrator.py   PIPELINE, persistence, tracing, progress
      specialists.py    the eight agents
      base.py           BaseAgent, AnalysisContext, AgentResult, SHARED_SYSTEM_RULES
      provider.py       AnthropicProvider | OfflineProvider selection
      offline_engine.py deterministic task implementations and explicit refusals
      lexicon.py        curated terms and patterns (recall floor for entities)
      report.py         claims → report structure
    astronomy/          timescales, ephemeris, events, catalogs, service — PURE, no I/O
                        dating_search.py orchestrates service.py the other way round:
                        a described sky in, ranked candidate dates out
    calendars/          core (Rata Die arithmetic), service (specs + caveats) — PURE
    knowledge/          corpus, embeddings, rag, seed
    api/v1/routers/     health, auth, analyses, exports, uploads, search, library,
                        reference (astronomy/calendars/corpus), admin
    services/           ingest, url_fetch, export, analysis_service, tagging
    db/                 30 ORM models + 2 association tables (32 tables), session
    core/               config, logging, security, rate_limit, middleware
    workers/            runner (background jobs), seed_cli
  alembic/versions/     6 migrations
  scripts/              create_admin.py, import_dataset.py, entrypoint.sh
  tests/                15 files, 435 tests collected
frontend/
  app/                  App Router pages (/, /analysis/[id], /dashboard, /explore,
                        /tools, /login, /admin, /shared/[id], /about, /auth/callback)
  components/           ReportView, ClaimCard, SkyMap, Timeline, EntityTable,
                        CalendarConverter, EclipseFinder, ReasoningTrace, …
  lib/                  api.ts (client + token storage), claims.ts (presentation
                        contract), types.ts, embeds.ts
  middleware.ts         nonce-based CSP, Node.js runtime
  tests/unit|e2e/       vitest; Playwright e2e + a11y
docs/                   INSTALLATION, USER_GUIDE, API, ARCHITECTURE, DEVELOPER,
                        ADMINISTRATOR, DEPLOYMENT, GO_LIVE
deploy/                 Caddyfile, docker-compose.prod.yml
render.yaml             Render blueprint for the API
```

---

## The agent pipeline

Eight specialists run in dependency order (`PIPELINE` in `agents/orchestrator.py`), each
reading a shared `AnalysisContext` and writing only to its own `AgentResult`; the
orchestrator merges, so one agent cannot corrupt another's findings.

| # | Agent | Model? | Produces |
| --- | --- | --- | --- |
| 1 | `language` | yes | Language, script, register, translation |
| 2 | `source_identification` | yes | Corpus match, graded; the dating dispute |
| 3 | `entities` | lexicon **+** model | People, places, symbols, numbers, prophetic formulae |
| 4 | `calendar` | **no** | Date expressions, conversions, explicit blockers |
| 5 | `astronomy` | **no** | Detected references; computed sky; correlations as hypotheses |
| 6 | `historical_context` | yes | Period, setting, audience, scholarly disputes |
| 7 | `interpretation` | yes | Traditional, scholarly and alternative readings |
| 8 | `evidence` | yes | An audit of the other seven |

### The dating pipeline

`mode` in an analysis's options selects which pipeline runs (`pipeline_for()` in
`orchestrator.py`). `analyze` is the default and is untouched by any of this. The four
dating modes — `date`, `rectification`, `eschatological`, `historicizing` — run a shorter
pipeline that drops the interpretation stage and ends with a dating agent, so the ordinary
path's cost and latency are exactly what they were.

`AstronomicalDatingAgent` (free) and `AdvancedDatingAgent` (the three paid modes) are the
inverse of `AstronomyAgent`: given the phenomena the lexicon found, they search a span for
dates whose real sky matches, and emit one `astronomical_dating_candidate` per candidate.
Both are deterministic — no model is consulted anywhere in the mode.

This is a *requested* mode rather than a pipeline step for the same reason the astronomy
agent declines to correlate unasked: over a wide enough span something always matches.
Every candidate therefore carries the criteria it failed, and a candidate resting only on
common phenomena (an eclipse, a season) says so in its own notes.

Invariants to preserve:

- **Agents 4 and 5 must never call a language model.** Their output is arithmetic; routing
  it through a model adds no capability and one failure mode. They call the pure engines
  and emit `astronomical_calculation` claims naming the algorithm, with
  `provider="deterministic"`.
- **Failure is partial, never total.** `BaseAgent.execute()` catches; a failing agent
  degrades to a `skipped` result and marks its section unavailable while the rest of the
  report still renders. Never let an agent raise out of `run()`.
- **Every agent sets `reasoning_summary`.** It is shown to the user in the explainability
  panel. Say what the method was and what its limits are — "extracted 12 entities" is
  useless.
- **Eschatological and historicizing output may never be typed as evidence.** Enforced in
  `coerce_claim()`, scoped to the dating agents by name: the astronomy agent still emits
  real `astronomical_calculation` claims in those modes, because "an eclipse occurred on
  this date" is true whatever mode asked. The mode comes from the analysis's own options,
  never from the agent, so an agent cannot exempt itself.
- **The astronomy agent declines to correlate when the text supplies no date.** Ancient
  texts use eclipse imagery constantly; matching a nearby eclipse to "the moon became as
  blood" produces a confident match every time and every one is meaningless. This
  restraint is deliberate — do not "improve" it into a search.

### The offline provider is not a stub

`AI_PROVIDER=auto` (the default) uses Anthropic when `ANTHROPIC_API_KEY` is set and the
deterministic engine otherwise. The offline engine does real work — Unicode script
detection, function-word language profiling, lexicon extraction, a date grammar, corpus
grading — routed by an inert `<task>name</task>` tag in the prompt that a real model reads
as ordinary structure.

Where a task needs genuine synthesis it returns
`{"offline_unavailable": true, "reason": "..."}` and the calling agent reports the section
as unavailable. **That refusal is the point.** A rule engine emitting plausible-sounding
"traditional interpretations" is exactly the failure mode this platform exists to prevent.

When you add a model-calling agent, tag its prompt and add either a handler or an explicit
refusal in `agents/offline_engine.py` — otherwise the offline path silently degrades.

---

## Tiers, entitlements and billing

Two orthogonal axes, and confusing them is the easiest way to break this:

- **`Role`** (`VIEWER < USER < RESEARCHER < MODERATOR < ADMIN`) — what an account may
  *administer*. Checked with `require_admin` and friends in `api/deps.py`.
- **`Tier`** (`free`, `paid`, `byok`) — what an account has *paid for*. Set only by the
  Stripe webhook in `services/billing.py`.

`services/entitlements.py` is the single place the paid question is answered. Its
docstring is the specification; `unlocks_interpretation()` is the one function, and
`require_paid_tier` in `api/deps.py` delegates to it rather than repeating the rule.
Never inline a `user.tier` check anywhere else — three separate code paths deliver claim
text to a reader (the claim list, the embedded report structure, and five export formats,
which read the ORM directly and bypass the router's serialiser entirely) and they must
agree. `tests/test_billing.py` asserts each path independently for that reason.

Locking is **not** deletion. A withheld claim keeps its id, type, section, ordering,
confidence and references; only the readable fields are replaced. This keeps the
claim-type counts honest and is the same principle as the contract's visible downgrade.

**Administrators bypass paid-tier checks**, whatever their tier — the deliberate, narrow
exception to the separation above, so the operator can use the product on their own
account. It is decided per request and writes nothing: no tier change, no Stripe
customer, no billing state. Do not widen it into "roles imply tiers" anywhere else.

`entitlements.py` also owns the **astronomical dating allowance**: five searches for the
life of a free account (`FREE_DATING_SEARCHES`), counted as `COUNT(*)` over
`AstronomicalDatingUsage` rows. Lifetime rather than monthly on purpose — a resetting
quota needs something to run at the period boundary, and this deployment has no background
worker by design, so a monthly limit would be one that silently never reset. Span caps:
500 years free, 5,000 paid, applied by the API and clamped again in the agent. Admins are
not metered and no usage row is written for them.

Webhook handling is idempotent through a `ProcessedStripeEvent` ledger keyed by the
Stripe event id — Stripe redelivers, and a replayed activation must not re-grant a tier
the customer has since cancelled. The signature is verified before anything is written.

BYOK is a **stub** — the tier exists and the pricing page says "coming soon", but no key
is accepted anywhere yet. When it is implemented: a user-supplied Anthropic key is never
written to any table. It is accepted per request and only its last four characters are
persisted (`users.byok_anthropic_key_last4`), so a reader can tell which key is in use.
Persisting the full key as a shortcut is not an option.

---

## Conventions

**Comments explain *why*.** The code says what it does. A comment earns its place by
recording a decision, a constraint, or a trap. This codebase is unusually heavily
commented in exactly that style (see `next.config.mjs`, `middleware.ts`,
`core/config.py`, `pyproject.toml`) — match it. Several comments document production
incidents; do not delete them when touching nearby code.

**Errors are for the person reading them.** Say what went wrong *and what to do about it*.
The config validators are the model to follow.

**Uncertainty is data, not prose.** If something is approximate it carries a field saying
so: `is_exact`, `uncertainty_note`, `accuracy_note`, `confidence_basis`, `blocker`. These
exist so the honesty survives serialisation into a PDF.

**Tests assert against external sources.** Astronomy tests check Meeus' worked examples
and the NASA canon; calendar tests check published festival dates. A test that only
asserts self-consistency passes on a systematically wrong implementation.

**Assert the product promise, not the implementation.** e.g. "no uncited
`verified_history` reaches the client" catches regressions anywhere in the chain — agent,
contract, persistence, serialisation.

**Do not mock the API in e2e tests.** The bugs worth catching there are integration bugs.
A real one: the serialiser emitted `citations` where the schema and exporters expected
`references`; every unit test passed while the report crashed and exports silently lost
their citations.

### Backend specifics

- Routers stay thin: validate, authorise, delegate. Pydantic schemas in `app/schemas/`,
  business logic in `app/services/`.
- `CurrentUser` requires auth; `OptionalUser` allows anonymous.
- Add `dependencies=[Depends(rate_limiter("bucket"))]` to anything expensive.
- Call `record_audit(...)` for anything that changes state or reads someone's data.
- Return **404, not 403**, for resources the caller does not own — a 403 confirms the id
  exists.
- Ruff: line length 100, `E,F,I,UP,B,S,C4`. Enums deliberately inherit from `str` rather
  than `StrEnum` (`UP042` is ignored) because SQLAlchemy's `Enum(native_enum=False)` and
  Pydantic rely on the member being a real `str`.
- Both astronomy and calendars are **pure**: no database, no network, no configuration.
  Keep them that way — it is what makes them testable against published values and lets
  the same code serve the pipeline and the public API.
- Every calendar conversion routes through Rata Die day numbers, so implementing
  `to_rd`/`from_rd` gives every pairwise conversion for free. `caveat` is mandatory when
  `CalendarSpec.exact=False`, and a test enforces it.
- Astronomical year numbering throughout: year 0 = 1 BCE, −1 = 2 BCE.

### Frontend specifics

- `lib/claims.ts` is the UI half of the epistemic contract: every claim type's label,
  description, badge, border, icon and `isEvidence` flag. **Every surface renders through
  it** — never inline claim styling in a component. The backend also ships a
  `presentation` block per claim, so a client cannot drift from what the backend enforces.
- **Colour is never the only signal.** Every badge carries an icon *and* a text label; the
  a11y suite verifies the labelling survives with all colour stripped.
- Confidence is a bar *and* a percentage *and* a band name *and* an `aria-label`.
- Design tokens live in `tailwind.config.ts` ("a manuscript read by night"): `ink`
  neutrals, `lapis` primary, plus `verdigris`/`reed`/`gold`/`plum`/`terra`/`crimson` for
  claim types and danger. Use the named families, not raw hex or stock Tailwind colours.
  Display headings are Bodoni Moda (`font-display`), body copy Spectral (`font-body`).
- Dark mode is `class`-based via `ThemeProvider`.
- Two credentials exist and are not interchangeable: a bearer token for an account, and a
  per-analysis **anonymous capability token** in `localStorage` that is the only way an
  unauthenticated visitor retrieves their result. There is no server-side recovery.
- Target: **zero WCAG 2.1 A/AA violations** on every page in both themes.

---

## Configuration

Everything is environment-driven via `backend/app/core/config.py` (`Settings`). Nothing
secret has a usable default — the app **refuses to boot in production** if `SECRET_KEY` is
still the sentinel, `DEBUG` is true, `CORS_ORIGINS` is `*`, or `DATABASE_URL` points at
loopback (unless `ALLOW_LOCAL_DATABASE=true`).

Values you will actually touch:

| Variable | Notes |
| --- | --- |
| `AI_PROVIDER` | `auto` (default) \| `anthropic` \| `offline`. Force `offline` for deterministic, fast runs while debugging anything that is not the model. |
| `ANTHROPIC_API_KEY` | Optional. Absent ⇒ offline engine, a fully supported mode. |
| `AI_MODEL` / `AI_FAST_MODEL` | `claude-opus-5` / `claude-haiku-4-5-20251001`. |
| `DATABASE_URL` | Bare `postgresql://`/`postgres://` URLs are rewritten to `postgresql+psycopg://` automatically, so a managed platform's own connection string works as pasted. |
| `NEXT_PUBLIC_API_URL` | **Baked into the browser bundle at build time.** Must match the backend's `CORS_ORIGINS` and the CSP `connect-src`. `next.config.mjs` fails the production build rather than shipping a bundle pointing at localhost; set `NEXT_PUBLIC_ALLOW_LOCALHOST=true` to do it deliberately (CI does). |
| `SWEEP_STALE_JOBS_IN_API` | On by default so a deployment with no separate worker still recovers jobs abandoned by a killed process. Turn off when running `app.workers.runner`. |
| `ALLOW_PASSWORD_REGISTRATION` | Off by default — there is no password-reset flow. The first admin is created out of band with `backend/scripts/create_admin.py`. |

---

## CI

`.github/workflows/ci.yml` runs on pushes to `main` and `claude/**`, and on PRs to `main`:

| Job | What it does |
| --- | --- |
| `backend` | Clean-install import check of every module, ruff lint, `ruff format --check`, mypy (non-blocking), pytest with coverage |
| `postgres-tests` | The same suite against real PostgreSQL + pgvector — SQLite silently accepts things Postgres rejects, and the pgvector retrieval path shipped broken twice |
| `migrations` | `upgrade head` → seed → `downgrade base` → `upgrade head` → `alembic check` |
| `frontend` | lint, typecheck, vitest, production build |
| `e2e` | Real API on `:8100` + real Next build; Playwright e2e and accessibility |
| `security` | pip-audit, npm audit, and a hard failure if a credential pattern is committed |
| `docker` | Both images build, and the API image must boot and answer `/api/v1/health/live` |

The clean-install import job exists because a missing `pydantic[email]` built fine and
crashed at startup — `EmailStr` imports `email-validator` at class-definition time. Any
new runtime dependency must be declared in `pyproject.toml`, not merely present locally.

---

## Testing map

| File | Covers |
| --- | --- |
| `tests/test_contracts.py` | **The epistemic contract — read as the specification** |
| `tests/test_calendars.py` | Conversions against published dates; round trips |
| `tests/test_astronomy.py` | Meeus examples, NASA values, historical anchor eclipses |
| `tests/test_dating_search.py` | The inverse search, incl. rediscovering the 7 BCE triple conjunction |
| `tests/test_dating_quota.py` | Who may run a dating search, how often, over how many years |
| `tests/test_agents.py` | Lexicon, offline engine, retrieval, orchestrator |
| `tests/test_api.py` | HTTP surface end to end |
| `tests/test_ingest_security.py` | Passwords, tokens, upload safety, SSRF, rate limits |
| `tests/test_job_recovery.py` | Stale-job sweep |
| `tests/test_config.py`, `test_db_config_is_shared.py`, `test_schema_widths.py` | Settings and schema invariants |
| `tests/test_import_dataset.py`, `test_admin_script.py` | The provenance gate and admin creation |

`tests/conftest.py` sets `ENVIRONMENT=test`, SQLite, `AI_PROVIDER=offline` and a temp
upload dir **before** any app module imports settings — keep new imports below that block.
Fixtures: `db`, `client`, `user_factory`, `auth_headers`, `sample_text`, `tmp_upload_dir`.

---

## Debugging

- `GET /api/v1/analyses/{id}/trace` — which agent produced what, on which model, with what
  reasoning and how long it took. Start here for "why did the analysis say that".
- `LOG_FORMAT=console` for readable local logs; every line carries a request id.
- `AI_PROVIDER=offline` makes runs deterministic and fast.
- Run the pipeline directly:

```python
from app.db.session import session_scope
from app.agents.orchestrator import run_analysis
from app.db.models import Analysis

with session_scope() as db:
    run_analysis(db, db.get(Analysis, "…"))
```

### Traps that have already cost time

- **Vercel's production branch is a dashboard setting, and it was wrong for two
  releases.** It pointed at `claude/ancient-text-analysis-platform-vz2p15` while `main`
  was the default branch, so a merge to `main` built as a *preview*: green, READY, and
  invisible on astro-decoded.com. It swallowed the billing admin override and the
  astronomical dating feature before anyone noticed, and neither reported an error,
  because nothing had failed. Render deploys from `main` correctly, so the backend went
  live while the frontend did not — the API gained endpoints no deployed client could
  call. **Now set to `main`** (Settings → Environments → Production → Branch Tracking;
  it is not on the Git settings page). If the site ever stops tracking `main` again,
  check `target` on the newest deployment: `"production"` is right, `null` means it
  built as a preview and the setting has drifted.
- **Vercel must have the Next.js Framework Preset pinned** (`frontend/vercel.json`).
  Without it Vercel picks `middleware.ts` up with its framework-agnostic builder and every
  request 500s with `MIDDLEWARE_INVOCATION_FAILED` — against a `middleware.js` path
  Next.js never emits. If this recurs, check what Vercel deployed before changing code.
- **No Node.js globals in `middleware.ts`.** It runs in the Edge runtime; `Buffer` gets
  polyfilled with something that uses `__dirname` and throws at request time, not build
  time. The CSP nonce is a bare `crypto.randomUUID()` for that reason.
- **`middleware.ts` duplicates the embed constants from `lib/embeds.ts`** because Vercel's
  Edge bundler cannot resolve that cross-module import. Keep the two in sync.
- Do not re-add `experimental: { nodeMiddleware: true }` to `next.config.mjs` — Node.js
  middleware is stable in Next 15.5 and the key is unrecognised.

---

## Performance notes

An offline analysis of a short text completes in ~100 ms; with a model, latency is
dominated by the six model-calling agents. Where time goes when it is slow: OCR (seconds
per page, bounded at 50 pages), conjunction search (capped at 50 years), eclipse scans
(capped at 200 years). The in-process cosine scan used without pgvector is linear in
corpus size — fine at seed scale, use PostgreSQL with pgvector before growing the corpus.

---

## Boundaries — do not "fix" these

These are design decisions, stated in the README and enforced in code:

1. **No eclipse visibility from a named place.** ΔT uncertainty for ancient dates is tens
   of minutes, which moves the ground track by tens of degrees of longitude.
2. **Planetary positions are approximations** (0.3–0.6° over five millennia).
3. **The corpus is a demonstration set** — 14 works and 17 passages. Absence means nothing.
4. **The default embedder is lexical** and says so. Swapping it requires re-seeding and
   re-calibrating `MIN_SCORE` and the `match_strength` bands in `knowledge/rag.py`.
5. **Model-supplied citations are marked unverified** and never counted as evidence.
6. **No theological adjudication**, and no claim about the future presented as fact.

---

## Git workflow

- Work on a `claude/<topic>` branch; CI runs on `claude/**` pushes.
- Push with `git push -u origin <branch>`.
- Do not open a pull request unless explicitly asked.
- Never commit credentials — CI fails the build on `sk-ant-…` / `AKIA…` patterns.
