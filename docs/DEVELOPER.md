# Developer guide

How to work on Starcode: setup, conventions, and how to extend the parts you are most
likely to want to extend.

Read [ARCHITECTURE.md](ARCHITECTURE.md) first if you have not — the design rationale
matters more here than the file layout.

---

## Setup

```bash
# Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

export DATABASE_URL="sqlite:///./dev.db"
export ENVIRONMENT=development
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"

alembic upgrade head
python -m app.workers.seed_cli
uvicorn app.main:app --reload

# Frontend, in another terminal
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

SQLite and the offline provider are fully supported for development. You do not need
Postgres, Redis, or an API key to work on almost anything.

### The loop

```bash
cd backend
pytest -q                          # 271 tests, ~17s
pytest tests/test_astronomy.py -q  # one file
pytest -k "eclipse" -q             # by name
ruff check app tests --fix
ruff format app tests

cd frontend
npm test                           # vitest
npm run typecheck
npm run lint
```

End to end, when you have changed anything that crosses the boundary:

```bash
./scripts/e2e-backend.sh &         # from the repository root
cd frontend
NEXT_PUBLIC_API_URL=http://127.0.0.1:8100 npm run build
npx playwright test --project=chromium
```

---

## Conventions

**Comments explain *why*.** The code says what it does. A comment earns its place by
recording a decision, a constraint, or a trap — not by narrating the line below it.

**Errors are for the person reading them.** An error message should say what went wrong
and what to do about it. `"A regnal year is only convertible once the ruler's accession
date is fixed, and accession dates for ancient rulers are frequently disputed by years"`
is worth more than `"cannot convert"`.

**Uncertainty is data, not prose.** If something is approximate, it carries a field
saying so. `is_exact`, `uncertainty_note`, `accuracy_note`, `confidence_basis`,
`blocker` — these exist so the honesty survives serialisation into a PDF.

**Tests assert against external sources.** Astronomy tests check Meeus' worked examples
and NASA's canon. Calendar tests check published festival dates. A test that only asserts
self-consistency passes on a systematically wrong implementation.

---

## Adding a calendar system

1. Implement the pair in `app/calendars/core.py`:

```python
FOO_EPOCH = julian_to_rd(400, 3, 21)

def foo_to_rd(year: int, month: int, day: int) -> int: ...
def rd_to_foo(rd: int) -> tuple[int, int, int]: ...
```

Everything routes through Rata Die, so you only ever write the two functions — every
pairwise conversion comes free.

2. Register it in `app/calendars/service.py`:

```python
"foo": CalendarSpec(
    key="foo",
    name="Foo calendar",
    culture="…",
    kind="lunisolar",
    epoch_description="21 March 400 CE (Julian).",
    to_rd=core.foo_to_rd,
    from_rd=core.rd_to_foo,
    month_names=core.FOO_MONTH_NAMES,
    exact=False,
    caveat="Months began on observed sighting, so a conversion can be off by a day.",
    references=[_RD_REFERENCE],
),
```

`caveat` is not optional if `exact=False`. A test enforces that every inexact system
explains itself.

3. Test against **published dates** — a festival, a recorded event, a documented epoch —
   and add it to the round-trip parametrisation in `tests/test_calendars.py`.

---

## Adding an agent

```python
from app.agents.base import SHARED_SYSTEM_RULES, AgentResult, AnalysisContext, BaseAgent
from app.agents.contracts import ClaimType, Section

class GeographyAgent(BaseAgent):
    name = "geography"
    description = "geographic reconstruction"
    prompt_version = "1.0.0"

    SYSTEM = SHARED_SYSTEM_RULES + """
Your specific instructions here.
"""

    def run(self, ctx: AnalysisContext) -> AgentResult:
        result = AgentResult(agent_name=self.name)

        data, response = self.ask(self.SYSTEM, f"""<task>geography</task>
…

<text>
{ctx.excerpt(8000)}
</text>

Reply with JSON: …""")

        if self.unavailable(data):
            return self.offline_result(data, "Geographic reconstruction could not be produced.")

        for item in data.get("places", []):
            result.claims.append(self.make_claim(
                section=Section.HISTORICAL_CONTEXT,
                claim_type=ClaimType.AI_HYPOTHESIS,   # unless you can cite it
                statement=item["statement"],
                confidence=float(item.get("confidence") or 0.4),
                confidence_basis="…",
            ))

        result.reasoning_summary = "…"   # required: shown to the user
        return result
```

Then add it to `PIPELINE` in `app/agents/orchestrator.py` with a progress fraction.

Things to get right:

- **Choose the claim type honestly.** If you cannot cite it, it is an `ai_hypothesis`. The
  contract will downgrade it anyway; doing it deliberately is clearer.
- **Tag the prompt** with `<task>name</task>` so the offline engine can route it, and add
  a handler (or an explicit refusal) in `app/agents/offline_engine.py`.
- **Write a `reasoning_summary`.** It appears in the explainability panel. "Extracted 12
  entities" is useless; say what the method was and what its limits are.
- **Never raise.** `execute()` catches, but a failing agent should degrade to a `skipped`
  result with an explanation.

### Deterministic agents

If your work is computation rather than inference, do not call a model at all. Follow
`CalendarAgent`: call the pure engine, emit `astronomical_calculation` claims naming the
algorithm, set `provider="deterministic"`.

---

## Extending the corpus

Append to `app/knowledge/corpus.py` and reseed. Every entry needs real citations.

```python
{
    "slug": "book-of-enoch",
    "title": "1 Enoch (Ethiopic Book of Enoch)",
    "tradition": "apocrypha",
    "language": "Ge'ez (from a Greek original, from Aramaic)",
    "composition_earliest_year": -300,
    "composition_latest_year": -100,
    "dating_note": (
        "Composite. The Astronomical Book (chs. 72–82) is attested at Qumran in "
        "Aramaic fragments from the 3rd century BCE; the Parables (chs. 37–71) are "
        "generally dated much later and are absent from Qumran, which is the crux of "
        "the argument about their date."
    ),
    "canonical_citation": "1 Enoch; trans. R. H. Charles (1917), public domain.",
    "reliability": "contested_dating",
    "license": "Charles translation public domain",
}
```

**`dating_note` is the field that matters.** When a text was written determines whether
it could have been written before the events it appears to describe — which is the whole
question for most prophetic material. Record the actual disagreement, not a smoothed
single number.

Passages go in `SOURCE_PASSAGES`. Their `notes` field is indexed separately from the
translation, so a user quoting the verse retrieves the verse and a user asking a question
about it retrieves the caveat.

Use public-domain translations, credited. Then:

```bash
python -m app.workers.seed_cli   # idempotent
```

For bulk data, use `scripts/import_dataset.py`, which takes the same shapes as JSON:

```bash
python3 scripts/import_dataset.py corpus.json --dry-run
python3 scripts/import_dataset.py corpus.json
```

It validates the whole file before writing anything and refuses entries without
provenance — no citation, no credited translation, or an event described as recorded that
names no record. Keep that gate in mind if you extend it: it is where the epistemic
contract is enforced at ingest, so nothing unattributable reaches the retrieval index and
gets cited in a report. Its tests are in `tests/test_import_dataset.py`.

---

## Swapping the embedder

The default is lexical and says so. To use a neural encoder:

```python
from app.knowledge.embeddings import Embedder, set_embedder

class SentenceTransformerEmbedder:
    model_name = "all-MiniLM-L6-v2"
    dimensions = 384

    def __init__(self):
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(self.model_name)

    def embed(self, text: str) -> list[float]:
        return self._model.encode(text, normalize_embeddings=True).tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts, normalize_embeddings=True).tolist()

set_embedder(SentenceTransformerEmbedder())
```

Keep `dimensions` at 384 or change `EMBEDDING_DIM` and migrate the column.

**Re-seed after swapping** — existing vectors were produced by the old model and are
meaningless to the new one. And **re-check the thresholds** in `app/knowledge/rag.py`:
`MIN_SCORE` and the `match_strength` bands are calibrated to the lexical encoder's score
distribution, not universal constants.

---

## Adding an API endpoint

Routers stay thin: validate, authorise, delegate.

```python
@router.get("/things/{thing_id}", response_model=ThingOut)
def get_thing(thing_id: str, db: DbSession, user: CurrentUser) -> ThingOut:
    thing = db.get(Thing, thing_id)
    if thing is None or thing.owner_id != user.id:
        # 404 rather than 403: a 403 confirms the id exists.
        raise HTTPException(status_code=404, detail="No such thing.")
    return ThingOut.model_validate(thing)
```

Conventions:

- Pydantic schemas in `app/schemas/`, business logic in `app/services/`.
- `CurrentUser` requires auth; `OptionalUser` allows anonymous.
- Add `dependencies=[Depends(rate_limiter("bucket"))]` to anything expensive.
- Call `record_audit(...)` for anything that changes state or reads someone's data.
- Return 404, not 403, for resources the caller does not own.

---

## Database changes

```bash
# edit app/db/models/*.py
alembic revision --autogenerate -m "add thing table"
# READ the generated file — autogenerate is a first draft, not an answer
alembic upgrade head
```

Check especially:

- Custom types render as `app.db.types.JSONBType()` / `VectorType()`, and the module is
  imported in the migration.
- Anything PostgreSQL-specific is guarded:
  `if op.get_bind().dialect.name == "postgresql":`
- `downgrade()` actually reverses `upgrade()`. CI runs the round trip.

CI also runs `alembic check`, which fails if the models and migrations disagree.

---

## Testing

| File | Covers |
| --- | --- |
| `test_calendars.py` | Conversions against published dates; round trips |
| `test_astronomy.py` | Meeus examples, NASA values, historical anchor eclipses |
| `test_contracts.py` | **The epistemic contract — read these as the specification** |
| `test_agents.py` | Lexicon, offline engine, retrieval, orchestrator |
| `test_api.py` | HTTP surface end to end |
| `test_ingest_security.py` | Passwords, tokens, upload safety, SSRF, rate limits |

Frontend: `tests/unit/` (vitest), `tests/e2e/` (Playwright), `tests/e2e/a11y.spec.ts`
(axe plus checks axe cannot make).

### Writing a good test here

Assert the *product promise*, not the implementation:

```python
def test_no_uncited_verified_history_reaches_the_client(self, client, sample_text):
    ...
    for claim in detail["claims"]:
        if claim["claim_type"] in ("verified_history", "scholarly_interpretation"):
            assert claim["references"], f"uncited: {claim['statement'][:80]}"
```

That test would catch a regression anywhere in the chain — agent, contract, persistence,
serialisation — because it checks what a user would actually receive.

### Don't mock the API in e2e

The bugs worth catching at that level are integration bugs. One real example: the report
serialiser emitted `citations` where the API schema and the exporters expected
`references`. Every unit test passed. The web report crashed and every export silently
lost its citations. A mocked API would have passed too.

---

## Debugging

**Structured logs.** `LOG_FORMAT=console` for readable local output. Every line carries a
request id.

**The trace endpoint.** `GET /api/v1/analyses/{id}/trace` shows which agent produced what,
on which model, with what reasoning and how long it took. Start here for "why did the
analysis say that".

**Force a provider.** `AI_PROVIDER=offline` makes runs deterministic and fast, which is
what you want while debugging anything that is not the model itself.

**Run the pipeline directly:**

```python
from app.db.session import session_scope
from app.agents.orchestrator import run_analysis
from app.db.models import Analysis

with session_scope() as db:
    analysis = db.get(Analysis, "…")
    run_analysis(db, analysis)
```

---

## Performance notes

An offline analysis of a short text completes in about 100 ms. With a model, latency is
dominated by the six model-calling agents.

Where the time actually goes when it is slow:

- **OCR**, seconds per page. Bounded at 50 pages.
- **Conjunction search**, which is a coarse scan plus golden-section refinement per pair.
  Capped at 50 years for that reason.
- **Eclipse scans**, capped at 200 years.

The in-process cosine scan used without pgvector is linear in corpus size. Fine at seed
scale; use PostgreSQL with pgvector before the corpus grows.

---

## Where things live

```
backend/app/
  agents/
    contracts.py     the epistemic contract — the most important file here
    orchestrator.py  pipeline, persistence, tracing
    specialists.py   the eight agents
    provider.py      Anthropic + offline
    offline_engine.py deterministic implementations and explicit refusals
    lexicon.py       curated terms and patterns
    report.py        claims → report structure
  astronomy/         timescales, ephemeris, events, catalogs, service
  calendars/         core (RD arithmetic), service (with caveats)
  knowledge/         corpus, embeddings, rag, seed
  api/v1/routers/    HTTP
  services/          ingest, url_fetch, export, analysis_service, tagging
  db/                models, portable types, session
  core/              config, logging, security, rate_limit, middleware
  workers/           runner, seed_cli
backend/scripts/
  create_admin.py    the only route to the first administrator
  import_dataset.py  JSON corpus import, with the provenance gate
  entrypoint.sh      container start: migrate, then serve
```
