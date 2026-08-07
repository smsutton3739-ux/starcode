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
- [x] **M2 — Database**: SQLAlchemy 2.0 models (16 tables), Alembic migration, pgvector.
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

---

## Status log

| Date       | Module | Note |
| ---------- | ------ | ---- |
| 2026-08-07 | M0     | Monorepo scaffolded; plan + epistemic contract fixed first. |
| 2026-08-07 | M1–M2  | Backend core + 16-table schema + Alembic baseline. |
| 2026-08-07 | M3–M4  | Calendar + astronomy engines with unit tests against published values. |
| 2026-08-07 | M5–M6  | Knowledge corpus, RAG, 8-agent orchestrator w/ offline provider. |
| 2026-08-07 | M7–M9  | Ingestion, API surface, report assembly and exporters. |
| 2026-08-07 | M10    | Frontend: homepage, analysis view, dashboard, admin, sky map. |
| 2026-08-07 | M11–M13| Docker, CI, full docs, test suites green. |

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
