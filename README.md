# Starcode

**Paste any ancient text, manuscript, prophecy, or historical document.**

Starcode analyses ancient texts, historical documents, astronomical references and
traditional prophecies, and returns a structured report that separates what is
*established* from what is *interpreted* from what is *conjectured*.

One box. One button. A report you can check.

---

## The rule the whole system is built around

> **Speculation is never presented as established fact.**

That is not a matter of careful wording. Wording drifts, models improvise, and a
confident sentence reads the same whether or not anything backs it. So the rule is
enforced structurally: every statement the platform makes is stored with an explicit
type, and the rules for each type are checked in code before anything reaches a reader.

| Type | Meaning | Evidence? |
| --- | --- | --- |
| `source_text` | Quoted verbatim from your input | ✅ |
| `verified_history` | Attested in the historical record — **requires a citation to exist** | ✅ |
| `astronomical_calculation` | Computed by the ephemeris/calendar engines — **must name its engine** | ✅ |
| `textual_analysis` | An observation about the text itself | — |
| `traditional_interpretation` | What a tradition has held. Reported, not endorsed | — |
| `scholarly_interpretation` | A position argued in academia — **requires a citation** | — |
| `ai_hypothesis` | Model conjecture. Confidence **capped by policy** | — |
| `uncertain` | Genuinely undetermined | — |

A claim that cannot satisfy its type's rules is **downgraded, visibly**, and the
downgrade is recorded in the audit trail. It is neither silently dropped (which loses
information) nor silently promoted (which is the exact failure this product exists to
prevent).

See [`backend/app/agents/contracts.py`](backend/app/agents/contracts.py) for the
enforcement and [`backend/tests/test_contracts.py`](backend/tests/test_contracts.py) for
the specification.

---

## Quick start

```bash
git clone <this repository> starcode && cd starcode
cp .env.example .env
docker compose up --build
```

Then open **http://localhost:3000**.

**No API key is required.** Without `ANTHROPIC_API_KEY` the platform runs its
deterministic engine: language detection, entity extraction, date parsing, calendar
conversion and the full astronomy engine all work. The interpretive sections report
themselves as *unavailable* rather than being filled with generated-looking text.

To enable the language model, put a key in `.env` and restart:

```bash
ANTHROPIC_API_KEY=sk-ant-...
```

Running without Docker? See [docs/INSTALLATION.md](docs/INSTALLATION.md).

---

## What it does

### Automatic, on every submission

Detects language and script · translates if needed · identifies the source against a
curated corpus · extracts people, places, empires, religions, cultures, deities,
calendars, sacred numbers, symbols, prophecies and celestial objects · parses date
expressions · converts calendars · computes the real sky for any date it finds ·
gathers traditional and scholarly readings · audits its own evidence.

### The astronomy is real

Not lookups — computation, from published algorithms, offline and deterministic:

- **Eclipses** (Meeus ch. 54): date, type, magnitude, γ, duration
- **Lunar phases** (ch. 49), **equinoxes and solstices** (ch. 27)
- **Moon** (ch. 47, abridged ELP-2000/82) and **Sun** (ch. 25)
- **Planets** via the JPL/Standish Keplerian approximation, 3000 BCE – 3000 CE
- **Conjunctions**, retrogrades, meteor showers, recorded comets and supernovae

Validated against Meeus' own worked examples and the historical record. The engine
reproduces:

| Event | Expected | Computed |
| --- | --- | --- |
| Eclipse of Thales | 28 May 585 BCE (Julian) | ✅ exact |
| Assyrian Bur-Sagale eclipse | 15 June 763 BCE (Julian) | ✅ exact |
| 1999 total solar eclipse γ | 0.5062 (NASA) | 0.5058 |
| 2019 Jan lunar umbral magnitude | 1.1953 (NASA) | 1.193 |
| Moon position, Meeus ex. 47.a | λ 133.167°, β −3.229°, 368409.7 km | ✅ all three |
| 7 BCE Jupiter–Saturn triple conjunction | three passes, in Pisces | ✅ |

Every result carries its own accuracy. Eclipse notes differ by epoch. Conjunctions
convert model position error into an explicit **timing** uncertainty, because for a slow
pair like Jupiter and Saturn a few tenths of a degree is two weeks of date uncertainty.

### Twelve calendar systems

Gregorian · Julian · Hebrew · Islamic · Egyptian · Coptic · Ethiopic · Persian · Maya
Long Count/Haab/Tzolkin · Chinese sexagenary · Julian Day · plus AUC, Seleucid,
Olympiad, Anno Mundi and Anno Martyrum era labels.

Conversions run through Rata Die day numbers, so every pair is exact by construction.
Verified against Rosh Hashanah 5784/5785, Passover 5784, Nowruz 1403, 13.0.0.0.0 =
21 December 2012, and a round trip over ~1.4 million days for every convertible system.

Where a conversion *cannot* be exact — a regnal year with a disputed accession, a bare
duration with no anchor, a lunar calendar that began months on sighting — the report
says so and names the specific obstacle instead of inventing precision.

### Reports

Executive summary · original text · detected language · translation · source
identification · historical context · astronomical references · calendar conversion ·
timeline · key entities · symbolism · traditional interpretations · modern scholarly
views · alternative interpretations · evidence · confidence ratings · references ·
further reading.

Export to **PDF, DOCX, CSV, Markdown or JSON**. Every format preserves the claim-type
labelling — in the CSV it is a column — because an export that dropped the distinction
between a calculation and a conjecture would defeat the product.

---

## Architecture

```
                    ┌──────────────────────────────┐
   Browser  ───────▶│  Next.js 15 · React 19 · TS  │
                    │  Tailwind · nonce-based CSP  │
                    └───────────────┬──────────────┘
                                    │ REST
                    ┌───────────────▼──────────────┐
                    │  FastAPI · OAuth + JWT       │
                    │  RBAC · rate limits · audit  │
                    └───────────────┬──────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        │                           │                           │
┌───────▼────────┐    ┌─────────────▼────────────┐   ┌──────────▼─────────┐
│  8-agent       │    │  Deterministic engines   │   │  PostgreSQL        │
│  orchestrator  │    │  · astronomy (Meeus/JPL) │   │  + pgvector        │
│  Claude / offline   │  · calendars (RD)        │   │  30 tables         │
└────────────────┘    └──────────────────────────┘   └────────────────────┘
```

**Eight specialist agents** run in dependency order: language → source identification →
entities → calendar → astronomy → historical context → interpretation → evidence audit.

The **calendar and astronomy agents consult no language model at all**. Their output is
arithmetic; routing it through a model would add nothing but a way for it to be wrong.

Agent failure is **partial, never total** — a failed stage marks its section unavailable
and the other eleven still render. Every run is persisted with provider, model, prompt
version, timing and a reader-facing reasoning summary, so any conclusion traces back to
what produced it.

---

## Repository layout

```
backend/
  app/
    agents/       8 specialists, orchestrator, epistemic contract, offline engine
    astronomy/    Meeus + JPL implementations, catalogues, service facade
    calendars/    Rata Die conversion engine and service
    knowledge/    curated corpus, embeddings, RAG, seeding
    api/v1/       REST routers
    services/     ingestion, OCR, URL fetch, exports, analysis lifecycle
    db/           30 SQLAlchemy models, portable column types
    core/         config, logging, security, rate limiting, middleware
    workers/      background job runner, seed CLI
  alembic/        migrations
  tests/          271 tests
frontend/
  app/            App Router pages
  components/     report viewer, sky map, claim cards, converters
  lib/            API client, claim presentation, types
  tests/          22 unit, 19 e2e, 16 accessibility
docs/             installation, deployment, API, architecture, developer, admin, user
```

---

## Testing

```bash
cd backend && pytest                      # 271 tests, no services needed
cd frontend && npm test                   # 22 unit tests
./scripts/e2e-backend.sh &                # then, in frontend/
cd frontend && npx playwright test        # 19 e2e + 16 accessibility
```

The backend suite runs on SQLite with the offline provider, so it needs no database, no
network and no credentials. The e2e suite runs against a **real** FastAPI process and a
real pipeline — nothing is mocked, because the bugs worth catching at that level are
integration bugs, and a mocked API would pass while the product was broken. (It did,
once: see the commit that fixed `citations` vs `references`.)

Accessibility: **zero WCAG 2.1 A/AA violations** on every page in both themes, plus
checks axe cannot make — that claim types stay distinguishable with all colour stripped
out, that confidence is exposed to assistive technology and not carried by a bar's width
alone, and that the whole homepage flow is operable from the keyboard.

---

## What this cannot do

Stated plainly, so nothing here is mistaken for an oversight.

- **No eclipse visibility from a named place.** It establishes that an eclipse occurred,
  when, and of what type. For ancient dates the uncertainty in Earth's rotation (ΔT) is
  tens of minutes, which moves the ground track by tens of degrees of longitude. Any tool
  showing a precise ancient eclipse path is overselling its precision.
- **Planetary positions are approximations** — 0.3–0.6° over five millennia.
- **It does not adjudicate religious or interpretive questions.** It reports what
  traditions have held and what scholars argue, attributed and sourced.
- **It makes no claims about the future.** Prophetic material is described and readings
  attributed; a prediction is never presented as a fact about what will happen.
- **The reference corpus is a demonstration set** of ~30 curated works and passages. A
  text absent from it is not thereby unknown.
- **Model-supplied citations are marked unverified.** Language models invent
  plausible-looking references; anything not drawn from the curated corpus is labelled.

---

## Documentation

| Guide | For |
| --- | --- |
| [Installation](docs/INSTALLATION.md) | Getting it running, with and without Docker |
| [User guide](docs/USER_GUIDE.md) | Using the platform and reading a report honestly |
| [API](docs/API.md) | Every endpoint, with examples |
| [Architecture](docs/ARCHITECTURE.md) | How and why it is built this way |
| [Developer](docs/DEVELOPER.md) | Working on it: adding agents, calendars, corpus data |
| [Administrator](docs/ADMINISTRATOR.md) | Running it: users, monitoring, prompts, datasets |
| [Deployment](docs/DEPLOYMENT.md) | Vercel, AWS, environment, CI/CD |
| [Project plan](PROJECT_PLAN.md) | Module checklist and scope decisions |

---

## Licence

MIT. The curated corpus uses public-domain translations, credited individually; see
[`backend/app/knowledge/corpus.py`](backend/app/knowledge/corpus.py).

Starcode is a research aid, not a scholarly authority.
