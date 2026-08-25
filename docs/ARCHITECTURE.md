# Architecture

This document explains *why* the system is shaped the way it is. The decisions that
matter here are mostly about trust: how a platform that mixes calculation, scholarship,
tradition and machine conjecture can present all four without letting any of them borrow
the authority of another.

---

## 1. The central problem

A tool like this fails in a specific way. Given an ancient text, it is easy to produce
fluent, confident, plausible output — dates, correlations, interpretations — and almost
none of it is checkable. The failure is not that the output is *wrong*; it is that a
reader cannot tell which parts are wrong.

So the architecture is organised around one question: **for any given sentence, what kind
of thing is it, and what would it take to check it?**

### The claim as the unit of work

Nothing in Starcode produces prose directly. Agents produce **claims**, and a claim is a
record with a mandatory type:

```python
@dataclass
class ClaimDraft:
    section: Section
    claim_type: ClaimType      # mandatory
    statement: str
    confidence: float
    confidence_basis: str | None
    produced_by: str           # which agent
    engine: str | None         # which algorithm, for calculations
    citations: list[CitationDraft]
```

Prose is assembled from claims at the end. This inverts the usual arrangement — generate
text, then try to annotate it — and it is what makes the epistemic rules enforceable
rather than aspirational.

### The rules, and where they live

`app/agents/contracts.py`:

| Rule | Consequence |
| --- | --- |
| `verified_history` and `scholarly_interpretation` require ≥1 citation | Cannot be stored uncited |
| `astronomical_calculation` must name its engine | A number without provenance is a guess |
| `source_text` must carry the verbatim quotation | |
| `ai_hypothesis` confidence is capped at 0.55 | A model cannot argue itself into certainty |
| Hypotheses may not assert a future event as settled | Pattern-checked |

A violating claim is passed through `coerce_claim`, which **downgrades** it and records
the downgrade in `payload.contract_adjustments`.

Downgrading rather than rejecting is a deliberate choice. Dropping the claim loses
information a reader might want. Promoting it is the exact failure the product exists to
prevent. Downgrading, visibly, is the honest third option.

### Why this is not just prompt engineering

Prompts drift. Models improvise. A system prompt saying "always cite your sources"
produces cited-*looking* output, which is worse than uncited output because it is harder
to audit. The contract is applied *after* generation, on the way to the database, so an
agent's good intentions are irrelevant to whether the rule holds.

---

## 2. System shape

```
Browser ── Next.js 15 (App Router, RSC) ── nonce CSP via middleware
   │
   │ REST + JSON
   ▼
FastAPI ── middleware: request id → security headers → CSRF → CORS
   │
   ├── routers/    thin: validate, authorise, delegate
   ├── services/   ingestion, exports, analysis lifecycle
   ├── agents/     orchestrator + 8 specialists + contract
   ├── astronomy/  pure functions, no I/O
   ├── calendars/  pure functions, no I/O
   └── knowledge/  corpus, embeddings, retrieval
   │
   ▼
PostgreSQL + pgvector (30 tables) · Redis (rate limits, cache)
```

The astronomy and calendar packages are **pure**: no database, no network, no
configuration. That is what makes them testable against published reference values, and
what lets the same code serve both the analysis pipeline and the public API.

---

## 3. The agent pipeline

Eight specialists run in dependency order, each reading what earlier ones put into a
shared `AnalysisContext` and writing only to its own `AgentResult`. The orchestrator
merges, so one agent cannot corrupt another's findings.

| # | Agent | Uses a model? | Produces |
| --- | --- | --- | --- |
| 1 | `language` | yes | Language, script, register, translation |
| 2 | `source_identification` | yes | Corpus match, graded; the dating dispute |
| 3 | `entities` | lexicon **+** model | People, places, symbols, numbers, prophetic formulae |
| 4 | `calendar` | **no** | Date expressions, conversions, and stated blockers |
| 5 | `astronomy` | **no** | Detected references; computed sky; correlations as hypotheses |
| 6 | `historical_context` | yes | Period, setting, audience, scholarly disputes |
| 7 | `interpretation` | yes | Traditional, scholarly and alternative readings; symbolism |
| 8 | `evidence` | yes | An audit of the other seven |

### Why 4 and 5 use no model

Calendar conversion is arithmetic. Eclipse computation is arithmetic. Passing either
through a language model adds no capability and one failure mode. These agents call the
pure engines directly and emit `astronomical_calculation` claims naming the algorithm.

This also means the platform's most checkable output is its most reliable — the opposite
of the usual arrangement, where the parts that sound most authoritative are the parts
generated by the model.

### Why entity extraction runs both

The curated lexicon (`app/agents/lexicon.py`) gives recall a **floor** that does not
depend on a model behaving well, and exact character spans for every hit. The model adds
entities the lexicon does not know and disambiguates referents. Results are merged, and
corroboration is tracked — a lexicon hit the model also found is scored higher.

The two extraction confidences are kept separate on purpose:

- `extraction_confidence` — is this in the text at all?
- `identification_confidence` — *which* referent is it?

"Babylon" is near-certain as a mention and genuinely ambiguous as a referent — the city,
the empire, or Rome under a cipher. Collapsing those into one number would hide the
interesting part.

### How the astronomy agent avoids manufacturing coincidences

It separates three different statements:

1. *"The text mentions an eclipse"* — `source_text`, confidence 0.9
2. *"An eclipse occurred in 587 BCE"* — `astronomical_calculation`, confidence 0.9
3. *"This text may refer to that eclipse"* — `ai_hypothesis`, confidence 0.3

And when the text supplies no date, it declines step 3 entirely, saying so:

> Without a date, any eclipse could be matched to the passage — and over a few centuries
> there are thousands. A match found that way carries no evidential weight.

This is the single most important restraint in the system. Ancient prophetic texts use
eclipse imagery constantly; a tool that searched for a nearby eclipse whenever it saw
"the moon became as blood" would produce a confident match every time, and every one
would be meaningless.

### Failure is partial

An agent that fails marks its section unavailable; the other eleven still render. A user
who pasted a manuscript gets what worked. The executive summary names the gaps.

---

## 4. The AI provider layer

```
LLMProvider (protocol)
├── AnthropicProvider   when ANTHROPIC_API_KEY is set
└── OfflineProvider     deterministic, rule-based
```

The offline provider is **not a stub**. It does real work — Unicode script detection,
function-word language profiling, lexicon extraction, a date grammar, corpus grading —
using the same prompts, routed by an inert `<task>name</task>` tag that a real model
simply reads as structure.

Where a task needs genuine synthesis, it returns:

```json
{ "offline_unavailable": true, "reason": "translation requires a language model" }
```

and the calling agent reports the section as unavailable.

**That refusal is the point.** A rule engine emitting plausible-sounding "traditional
interpretations" would be precisely the failure this platform exists to prevent. It is
better to have an empty section that says why than a full one that cannot be trusted.

This is also what makes the repository runnable by anyone who clones it, and what lets
325 tests run with no network and no credentials.

---

## 5. Data model

30 tables. The groupings that matter:

**Content** — `uploads` → `documents` → `analyses`. Uploads are content-addressed and
deduplicated per owner (re-OCR is expensive and produces the same answer). Documents are
deduplicated by content hash; analyses are *not*, because re-analysing the same text
after a model or corpus change is a legitimate action.

**Claims** — the epistemic vocabulary lives in `claims.claim_type` as a constrained enum,
with a check constraint on confidence range. `references` link to claims, and carry a
`verified` flag that is true only for citations from the curated corpus.

**Knowledge** — `historical_sources` carry a `dating_note` field recording *why* a date
range is what it is. `astronomical_events` carry `is_computed`, distinguishing a
calculated event from one attested in a document — both useful, not the same kind of
evidence.

**Operations** — `audit_logs` is append-only, with no update route and denormalised
actor email so the trail survives account deletion. IPs are hashed: enough to correlate
abuse, not enough to identify a person.

### Portable column types

`JSONBType` and `VectorType` resolve per dialect: JSONB and `vector(384)` on PostgreSQL,
JSON and TEXT elsewhere. This is why the entire test suite runs on SQLite with no
services, and why the same Alembic migration works against both.

---

## 6. Retrieval

The default embedder is **lexical**: hashed word, bigram and character-4-gram features,
signed-hash, L2-normalised to 384 dimensions.

This is stated plainly rather than dressed up. It captures vocabulary, morphology and
phrasing; it does not capture meaning the way a trained encoder does. "The moon turned to
blood" and "lunar eclipse" are close for a human and far apart here.

It is the default because it needs no model download, no GPU and no API call, so search
works identically offline and in CI — and because the retrieval job here is largely
lexical: matching a quoted passage to a corpus entry.

Swapping it is a single interface:

```python
class Embedder(Protocol):
    model_name: str
    dimensions: int
    def embed(self, text: str) -> list[float]: ...
```

`set_embedder()` replaces it; the pgvector column, the RAG layer and the search API need
no changes.

### Guarding against false matches

Every hit carries a cosine score **and** a Jaccard token-overlap cross-check. A high
cosine with near-zero shared vocabulary is a hashing artefact, not a match, and is
dropped. Results below a floor are withheld entirely rather than shown with a low score —
a bad match presented as a source manufactures a citation that looks authoritative.

Thresholds are calibrated against the corpus, not guessed: a verbatim quote lands at
~0.55 cosine with ~0.30 overlap; a thematically related query lands near 0.30 with ~0.07.

---

## 7. Astronomy

Pure Python, no ephemeris files, no network.

| Target | Model | Accuracy |
| --- | --- | --- |
| Sun | Meeus ch. 25 | ~0.01° |
| Moon | Meeus ch. 47 (abridged ELP-2000/82) | ~10″ |
| Planets | JPL/Standish Keplerian, 3000 BCE–3000 CE | 0.3–0.6° |
| Eclipses | Meeus ch. 54 | γ to ~0.0005 (modern) |
| Phases, seasons | Meeus ch. 49, 27 | sub-minute |

Validation is against **external** sources — Meeus' worked examples, the NASA Five
Millennium Canon, and the historical anchor eclipses — never against this implementation's
own output. A test that only asserts self-consistency passes on a systematically wrong
implementation.

### ΔT and why it constrains what can be claimed

TT is smooth; UT tracks the Earth's irregular rotation. ΔT = TT − UT must be modelled,
and before telescopic records it is *estimated from ancient eclipse observations
themselves*.

For 1000 BCE the uncertainty is hours. That does not blur *whether* an eclipse
happened — that is orbital mechanics — but it moves the sub-solar point by tens of degrees
of longitude. So the engine reports eclipse dates confidently and eclipse *visibility from
a named place* only as an explicit uncertainty band. `time_uncertainty()` converts the ΔT
error directly into degrees of longitude, and every eclipse result carries it.

### Conjunction timing

Position error converts into date error at a rate set by the pair's relative angular
velocity — not by the change in separation, which is stationary at the minimum by
definition. For Jupiter and Saturn, 0.58° of model error is roughly ±13 days. Each
conjunction reports that figure, because "the conjunction is real, the exact day is not
pinned down" is a materially different statement from a bare date.

---

## 8. Calendars

Every system converts through **Rata Die** fixed day numbers (Dershowitz & Reingold), so
every pairwise conversion is exact by construction rather than by pairwise implementation.

Two conventions, stated because mixing them is the commonest source of off-by-one-year
errors in historical work:

- **Astronomical year numbering** throughout: year 0 = 1 BCE, −1 = 2 BCE.
- **Proleptic extension** is a *label*, not a claim anyone used that date.

Where exactness is impossible the engine still converts, and attaches the reason: tabular
versus observed lunar months, an unfixed regnal accession, a correlation constant with
competing values. `gregorian_range_for_year()` exists because most ancient dates are known
only to the year, and returning a *span* is the difference between "1446 AH means 2024"
and "1446 AH covers part of 2024 and part of 2025".

---

## 9. Security

| Concern | Approach |
| --- | --- |
| Passwords | bcrypt directly, cost 12; over-72-byte inputs rejected, not truncated |
| Sessions | JWT with a `typ` claim — a refresh token is not accepted as an access token |
| Share tokens | Stored as a keyed HMAC; plaintext shown once, unrecoverable |
| SQL injection | Parameterised throughout via SQLAlchemy; no string-built SQL |
| XSS | React escaping, plus a nonce-based CSP with no `unsafe-inline` for script |
| CSRF | Bearer auth is not CSRF-able; origin checking for the cookie path |
| Uploads | Content sniffing, not extension trust; HTML/script refused; content-addressed storage |
| SSRF | Hostname resolved and checked before connecting, **re-checked after every redirect** |
| Enumeration | 404 rather than 403; registration cannot confirm an address |
| Timing | Password verification runs even for a missing account |
| Audit | Append-only, hashed IPs, denormalised actor email |

The nonce CSP is worth a note. Next.js App Router bootstraps with inline scripts, so a
policy without `unsafe-inline` blocks the app unless each script is nonced. Rather than
open `script-src` — the protection worth having in an app that renders user-submitted
text — a nonce is minted per request in `middleware.ts`. The cost is that pages render on
demand rather than being prerendered; for this app that is close to free.

---

## 10. Frontend

The presentation half of the contract lives in `lib/claims.ts`: every claim type has a
label, description, badge colour, border, icon and an `isEvidence` flag. Every surface
renders through it. The backend also ships a `presentation` block with each claim, so a
client that fetches it can never drift from what the backend enforces.

Colour is never the only signal. Each badge carries an icon *and* a text label, and the
accessibility suite verifies the labelling survives with all colour stripped out.

Confidence is a bar *and* a percentage *and* a band name *and* an `aria-label` — a bar
with no accessible name is invisible to a screen reader, and confidence is the most
important qualifier in the report.

---

## 11. Known limitations

Design boundaries, not defects:

1. **No eclipse ground track.** Establishing whether an eclipse was visible from a named
   place requires geometry the ΔT uncertainty would not support for ancient dates.
2. **Planetary positions are approximations.** Fine for "which sign", not for occultation
   timing.
3. **The corpus is a demonstration set.** ~30 curated works. Absence means nothing.
4. **The default embedder is lexical.** Conceptual paraphrase retrieval is weak.
5. **Translation quality is not verified.** Machine translation of ancient languages is
   flagged as low-confidence and the report says so.
6. **Model citations are unverified.** Marked as such, never counted as evidence.
7. **No theological adjudication.** By design, permanently.

---

## 12. Extending it

| To add… | Do this |
| --- | --- |
| A calendar | Implement `to_rd`/`from_rd` in `calendars/core.py`, register a `CalendarSpec` with its caveat |
| An agent | Subclass `BaseAgent`, implement `run()`, add to `PIPELINE` |
| Corpus data | Append to `knowledge/corpus.py` (or write an importer) and reseed |
| A neural embedder | Implement `Embedder`, call `set_embedder()` |
| A claim type | Extend `ClaimType`, `CLAIM_TYPE_PRESENTATION` and `lib/claims.ts`, and decide its rules |

The last one is deliberately the most involved. Adding a new kind of epistemic status
should require thinking about what it means, what it requires, and how it renders —
in that order.
