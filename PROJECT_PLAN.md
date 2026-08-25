# Starcode — Living Project Plan

**Product:** An AI-powered platform for analyzing ancient texts, historical documents,
astronomical references, and traditional prophecies.

**Core promise:** paste text → press one button → get a structured, sourced,
uncertainty-labelled report. Speculation is *never* presented as fact.

---

## Epistemic contract (the product's most important rule)

Every claim the platform emits carries a `claim_type` from a fixed vocabulary. The UI
renders each type with a distinct colour, icon and label, and the API refuses to store a
claim without one.

| `claim_type`             | Meaning                                                                 |
| ------------------------ | ----------------------------------------------------------------------- |
| `source_text`            | Verbatim quotation from the user's input. No interpretation.            |
| `verified_history`       | Event supported by the historical record and citable to a source.       |
| `astronomical_calculation` | Deterministic output of an ephemeris/calendar algorithm. Reproducible. |
| `textual_analysis`       | Observation about the text itself (language, structure, vocabulary).    |
| `traditional_interpretation` | What a religious/cultural tradition has historically held.          |
| `scholarly_interpretation` | A position held in peer-reviewed/academic literature.                 |
| `ai_hypothesis`          | Model-generated conjecture. Not evidence. Always labelled.              |
| `uncertain`              | Explicitly unknown / underdetermined.                                   |

Rules enforced in code (`backend/app/agents/contracts.py`):
1. A claim of type `verified_history` or `scholarly_interpretation` **must** carry ≥1 citation.
2. `ai_hypothesis` confidence is hard-capped (see `AI_HYPOTHESIS_CONFIDENCE_CAP`).
3. `astronomical_calculation` must carry the engine + algorithm reference that produced it.
4. Predictions about the future are only ever `ai_hypothesis` or `traditional_interpretation`.

---

## Module checklist

- [x] **M0 — Repo scaffolding**: monorepo layout, env management, tooling config.
- [x] **M1 — Backend core**: settings, structured logging, error handling, request IDs.
- [x] **M2 — Database**: SQLAlchemy 2.0 models (30 tables), Alembic migration, pgvector.
- [x] **M3 — Calendar engine**: 12 calendar systems, RD-based conversions, uncertainty notes.
- [x] **M4 — Astronomy engine**: Meeus algorithms — JD, moon phases, eclipses, equinoxes,
      planetary longitudes, conjunctions, retrogrades. Pure Python, deterministic, offline.
- [x] **M5 — Knowledge base**: curated seed corpus + citations + RAG index (pgvector w/ in-memory fallback).
- [x] **M6 — Multi-agent AI engine**: 8 specialist agents + orchestrator, retries, tracing,
      explainable reasoning summaries, deterministic offline provider.
- [x] **M7 — File processing**: PDF, DOCX, images/OCR, URL fetch, metadata, safety scanning.
- [x] **M8 — API layer**: REST v1, OAuth + JWT, RBAC, rate limits, validation, audit log.
- [x] **M9 — Reports & exports**: report assembly, PDF / DOCX / CSV / JSON / Markdown export.
- [x] **M10 — Frontend**: Next.js 15 App Router, one-box homepage, report viewer, dashboard,
      sky map, timeline, collections, admin, dark/light, a11y.
- [x] **M11 — Deployment**: Dockerfiles, docker-compose, Vercel + AWS notes, CI/CD.
- [x] **M12 — Testing**: unit, integration, API, a11y, e2e, performance smoke.
- [x] **M13 — Documentation**: README, install, deploy, API, architecture, developer, admin, user.
- [x] **M14 — Going live**: custom-domain configuration, build-time environment guard,
      accounts policy (OAuth + anonymous, no unrecoverable passwords), operator scripts
      for the first admin and for corpus import.

---

## Status log

| Date       | Module | Note |
| ---------- | ------ | ---- |
| 2026-08-07 | M0     | Monorepo scaffolded; plan + epistemic contract fixed first. |
| 2026-08-07 | M1–M2  | Backend core + 30-table schema + Alembic baseline. |
| 2026-08-07 | M3–M4  | Calendar + astronomy engines with unit tests against published values. |
| 2026-08-07 | M5–M6  | Knowledge corpus, RAG, 8-agent orchestrator w/ offline provider. |
| 2026-08-07 | M7–M9  | Ingestion, API surface, report assembly and exporters. |
| 2026-08-07 | M10    | Frontend: homepage, analysis view, dashboard, admin, sky map. |
| 2026-08-07 | M11–M13| Docker, CI, full docs, test suites green. |
| 2026-08-10 | —      | Shipped. 271 backend + 22 unit + 19 e2e + 16 a11y tests pass; zero WCAG A/AA violations; full flow verified in a browser. |
| 2026-08-10 | M14    | Deployment hardening for a real domain: build-time guard on `NEXT_PUBLIC_API_URL`, accounts decision (below), the two operator scripts the docs referenced, OAuth replica constraint documented. 295 backend tests. |
| 2026-08-25 | —      | CI green again, red since run 35 on 20 August: `package-lock.json` resynced so `npm ci` installs (the frontend and e2e jobs had been failing at Install, and the backend job's format check was gating its own test step). Two assertions left stale by the manuscript restyle fixed. Counts in this file and the docs re-measured against actual runs. |

### M14 — what shipped and why

- **Password registration is off by default** (`ALLOW_PASSWORD_REGISTRATION`). There is no
  reset flow, and an account nobody can recover is worse than none — the person who
  forgets it loses their saved analyses permanently. `POST /auth/register` answers 403
  with that reason rather than 404, and `GET /auth/oauth/providers` reports the
  deployment's real capabilities so the client hides a form the API would refuse. Existing
  password accounts still sign in, so an operator is never locked out.
- **`scripts/create_admin.py`** — creates or promotes an administrator from the shell.
  Without it, disabling registration would leave a fresh deployment with no route to its
  own admin panel. Passwords come from a hidden prompt or the environment, never from
  argv. Re-running changes a role without touching the credential; `--reset-password` is
  the recovery path.
- **`scripts/import_dataset.py`** — the corpus loader `corpus.py` and this plan had both
  been pointing at a script that did not exist. It validates the whole file before writing
  anything and refuses entries without provenance: no citation, no credited translation,
  or a "recorded" event that names no record. That is the epistemic contract enforced at
  the point of ingest rather than apologised for later.
- **Build guard corrected.** The first version keyed on `NODE_ENV=production`, which
  `next start` and `next lint` also set — so a correctly built Docker image refused to
  boot. It now fires on the build phase only, verified against all four commands.
- **OAuth needs one API replica** until its `state` store moves to Redis. Documented in
  `docs/DEPLOYMENT.md` with three ways to live with it, rather than left as a comment.

---

## Verification record

Every claim in the README is backed by something that was actually run.

| Check | Result |
| --- | --- |
| Backend tests | 325 passed (SQLite, offline provider, no network) |
| Frontend unit tests | 29 passed |
| End-to-end tests | 26 passed against a real FastAPI process |
| Accessibility tests | 20 passed; **zero** WCAG 2.1 A/AA violations, both themes |
| Lint + format | `ruff check` and `ruff format --check` clean |
| Type check | `tsc --noEmit` clean |
| Migration | Applies and reverses; `alembic check` agrees with the models |
| Entrypoint chain | `alembic upgrade head` → seed → worker start, all run directly |
| Browser walkthrough | Paste → ANALYZE → report, zero console errors |

External validation of the engines (not self-consistency):

| Anchor | Source | Result |
| --- | --- | --- |
| Eclipse of Thales | Herodotus 1.74; 28 May 585 BCE Julian | exact day |
| Bur-Sagale eclipse | Assyrian Eponym Canon; 15 June 763 BCE Julian | exact day |
| 1999 Aug 11 eclipse γ | NASA Five Millennium Canon: 0.5062 | 0.5058 |
| 2019 Jan lunar umbral mag. | NASA: 1.1953 | 1.193 |
| Moon position | Meeus example 47.a | λ, β and distance all match |
| Sun position | Meeus example 25.b | 0.001° |
| Lunar phase, solstice | Meeus examples 49.a, 49.b, 27.a | 1e-5 day |
| 7 BCE triple conjunction | Kepler's Star of Bethlehem proposal | three passes, in Pisces |
| Rosh Hashanah 5784/5785 | Published Hebrew calendar | exact |
| Nowruz 1403 | Published Persian calendar | exact |
| 13.0.0.0.0 | Maya Long Count, GMT correlation | 21 December 2012 |

Bugs found by verification rather than by writing more code:

1. `passlib` 1.7.4 misdetects bcrypt 4.1+ and rejected valid passwords — replaced with
   bcrypt directly.
2. Share expiry compared a naive datetime from SQLite against an aware `now()`, turning
   an authorisation check into a 500.
3. The orchestrator added a `Report` via `db.add()` after reading the cached relationship,
   so any caller holding the `Analysis` saw no report.
4. `ClaimDraft.to_dict()` emitted `citations` where the API schema and the exporters
   expected `references` — crashed the report view and silently dropped every citation
   from PDF, DOCX and Markdown exports. Both sides were individually correct, so only an
   unmocked end-to-end run could find it.
5. The Halley apparition table had century-wide gaps.
6. The hidden file input had no accessible name; "retrograde" failed contrast at 3.55:1.

---

## Deliberately out of scope (stated, not hidden)

These are named so nobody mistakes absence for oversight:

- **High-precision ephemerides.** The astronomy engine uses Meeus' abridged VSOP87/ELP
  series. Accuracy is ~±1–2 minutes for eclipse maxima near the present epoch, degrading to
  hours for dates before ~1000 BCE. This is stated in every astronomical result via the
  `accuracy_note` field. For publication-grade work, re-verify against JPL DE441.
- **Physical eclipse-path geometry.** The engine determines *whether and when* an eclipse
  occurred and its rough type/magnitude, not the precise ground track. ΔT uncertainty for
  ancient dates makes local visibility genuinely unresolvable without a full model; the
  engine returns a `visibility_uncertainty` band rather than a false-precision answer.
- **Automated theological adjudication.** The platform reports what traditions and scholars
  have said, attributed and sourced. It does not rule on which reading is correct.
- **The seed corpus is a demonstration corpus.** ~120 curated entries, all citable. It is
  not a substitute for a licensed scholarly database; the loader is built for expansion
  (`scripts/import_dataset.py`).
