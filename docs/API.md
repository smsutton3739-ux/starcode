# API reference

Base URL: `http://localhost:8000/api/v1`

Interactive documentation is served at `/docs` (Swagger) and `/redoc`. The OpenAPI
schema is at `/openapi.json`.

---

## Authentication

Two credentials exist, and they are not interchangeable.

**Bearer token** — for a signed-in account.

```http
Authorization: Bearer <access_token>
```

**Anonymous analysis token** — returned once when an unauthenticated visitor submits an
analysis, and the only way to retrieve it afterwards.

```http
X-Analysis-Token: <anonymous_token>
```

There is no server-side recovery for an anonymous token. That is the price of not
requiring a signup, and clients should say so before a user relies on it.

The same header also accepts a **share token**, so a shared report and an owned one are
fetched identically.

---

## Analyses

### `POST /analyses`

Submit something for analysis. Exactly one source field is required.

```json
{
  "text": "And the moon became as blood. In 587 BC Jerusalem fell.",
  "title": "Optional title",
  "options": {
    "detail_level": "standard",
    "astronomical_search_window_years": 5,
    "maya_correlation": 584283
  }
}
```

| Field | Type | Notes |
| --- | --- | --- |
| `text` | string | Up to `MAX_TEXT_CHARS` (400,000 by default) |
| `url` | string | Fetched server-side; see the SSRF protections below |
| `document_id` | string | From a previous upload |
| `upload_id` | string | From a previous upload |
| `title` | string | Optional |
| `project_id` | string | Optional |
| `options` | object | All fields optional and defaulted |

**`202 Accepted`**

```json
{
  "id": "a64cb7e1-...",
  "status": "queued",
  "progress": 0.0,
  "poll_url": "/api/v1/analyses/a64cb7e1-.../status",
  "anonymous_token": "kR3n...",
  "message": "Analysis started. Poll the status endpoint for progress. Keep the anonymous_token: without an account it is the only way to reach this analysis again."
}
```

`anonymous_token` is `null` for authenticated requests.

Errors: `400` (a URL could not be fetched, or a document is unusable), `422`
(no source, or more than one), `429` (rate limited — the body says when to retry).

### `GET /analyses/{id}/status`

Poll while it runs. Cheap; safe to call every few hundred milliseconds.

```json
{
  "id": "a64cb7e1-...",
  "status": "running",
  "progress": 0.52,
  "current_stage": "astronomy",
  "stage_label": "Checking the sky for those dates",
  "failed_stages": []
}
```

`status` is one of `queued`, `running`, `completed`, `partial`, `failed`, `cancelled`.

**`partial` is a success, not a failure**: at least one stage did not finish, the rest
did, and `failed_stages` names the gaps. Clients should render the report and say which
sections are missing.

### `GET /analyses/{id}`

The full analysis: claims, entities, the report, and the agent trace.

```json
{
  "id": "a64cb7e1-...",
  "title": "And the moon became as blood…",
  "status": "completed",
  "overall_confidence": 0.878,
  "confidence_rationale": "14 evidence-grade claims against 3 AI hypotheses. Confidence is weighted toward the verifiable material.",
  "detected_language": "en",
  "failed_stages": [],
  "claims": [
    {
      "id": "…",
      "section": "calendar_conversion",
      "claim_type": "astronomical_calculation",
      "statement": "“587 BC” converts to 26 December 588 BCE – 25 December 587 BCE.",
      "reasoning": "A bare year converts to a range rather than a date…",
      "confidence": 0.85,
      "confidence_basis": "Only a year was given, so the result is the Gregorian span…",
      "produced_by": "calendar",
      "engine": "starcode-calendars/1.0",
      "algorithm_reference": "Dershowitz & Reingold, Calendrical Calculations (4th ed., CUP, 2018)",
      "references": [],
      "presentation": {
        "label": "Astronomical calculation",
        "short": "Calculated",
        "description": "Computed by the platform's ephemeris and calendar engines…",
        "tone": "calculated"
      }
    }
  ],
  "entities": [...],
  "report": { "executive_summary": "...", "sections": [...], "timeline": [...] },
  "agent_runs": [...]
}
```

**Every claim ships with its `presentation` block.** Clients should render from it rather
than hard-coding labels, so the display can never drift from the enforcement.

`404` is returned both for an analysis that does not exist and for one you may not read.
This is deliberate: a `403` would confirm the id is real and leak the existence of other
users' work.

### `GET /analyses`

List your own analyses. Requires authentication.

Query: `limit` (1–100, default 20), `offset`, `status`, `favorites_only`, `project_id`,
`tag`, `q` (title substring).

### `PATCH /analyses/{id}`

```json
{ "title": "New title", "is_favorite": true, "tags": ["prophecy", "Revelation"] }
```

### `DELETE /analyses/{id}`

### `POST /analyses/{id}/rerun`

Re-analyse the same text as a **new** analysis with an incremented version. The original
is untouched — reports are dated artefacts, and overwriting one would silently invalidate
anything already shared or cited.

### `GET /analyses/{id}/trace`

The explainability trace: which agent produced what, on which model, how long it took,
and its own account of how it reached its conclusions.

```json
{
  "analysis_id": "…",
  "duration_ms": 98,
  "steps": [
    {
      "sequence": 4,
      "agent": "astronomy",
      "status": "succeeded",
      "provider": "deterministic",
      "model": "starcode-astronomy/1.0 (Meeus + JPL Keplerian)",
      "duration_ms": 2,
      "reasoning": "Detected 5 astronomical references. Computed the sky for 1 candidate year…",
      "claims_produced": 11
    }
  ],
  "claim_type_totals": [...]
}
```

---

## Uploads

### `POST /uploads`

`multipart/form-data` with a `file` field. Accepts PDF, DOCX, plain text, Markdown, and
PNG/JPEG/TIFF/WebP images (OCR'd automatically).

```json
{
  "upload": { "id": "…", "original_filename": "manuscript.pdf", "status": "ready" },
  "document_id": "…",
  "extracted_characters": 4821,
  "ocr_applied": true,
  "ocr_confidence": 78.4,
  "warnings": [
    "This PDF contained little or no embedded text, so OCR was used. OCR of historical documents makes systematic errors…"
  ],
  "preview": "And I beheld when he had opened…"
}
```

Pass `document_id` to `POST /analyses` to analyse it.

**Safety.** Files are identified by content, not by extension or by the declared MIME
type. HTML and script payloads are refused outright whatever they are named. Executable
extensions are refused. Filenames containing path separators or null bytes are refused.
Stored files are content-addressed, so a user's filename never touches a filesystem path.

### `POST /uploads/url`

```json
{ "url": "https://example.org/text" }
```

The fetcher resolves the hostname itself and refuses private, loopback, link-local and
cloud-metadata addresses, **re-checking after every redirect** — a public host can
redirect to `169.254.169.254`. Only `http` and `https` are accepted, size and time are
capped, and only extracted text is returned, never raw HTML.

### `GET /uploads/limits`

What this server accepts, for client-side validation.

---

## Exports

### `GET /analyses/{id}/export/{format}`

`format` is `pdf`, `docx`, `csv`, `markdown` or `json`.

Returns the file with `Content-Disposition: attachment`. Because the request needs an
`Authorization` or `X-Analysis-Token` header, a plain anchor will not work — fetch it and
save the blob.

Every format preserves the claim-type labelling. In the CSV it is a column, alongside an
`is_evidence` flag.

### `GET /analyses/{id}/export`

Lists available formats and whether the analysis is ready.

---

## Astronomy

Useful on their own — no analysis required. All are rate-limited but public.

### `GET /astronomy/sky`

`year` (−3000…3000, astronomical numbering: 0 = 1 BCE), `month`, `day`, `hour_ut`.

Returns positions for Sun, Moon and the five naked-eye planets, with **both** the
tropical zodiac sign and the IAU constellation, the moon phase, active meteor showers,
and the ΔT uncertainty for that epoch.

### `GET /astronomy/eclipses`

`start_year`, `end_year`, `kind` (`both`|`solar`|`lunar`). Capped at 200 years.

```json
{
  "count": 2,
  "events": [{
    "label": "Total solar eclipse",
    "gregorian_label": "21 August 2017 CE",
    "hour_ut": 18.4,
    "details": { "eclipse_kind": "total", "magnitude": 1.0, "gamma": 0.4364,
                 "visibility_uncertainty": "…" },
    "accuracy_note": "Computed from the Moon's argument of latitude at syzygy (Meeus ch. 54)…"
  }]
}
```

### Also available

| Endpoint | Returns |
| --- | --- |
| `GET /astronomy/eclipses/near` | Eclipses within a window of a date, nearest first |
| `GET /astronomy/moon-phases` | Phases across a year range |
| `GET /astronomy/moon` | The Moon on one date |
| `GET /astronomy/seasons` | Equinoxes and solstices |
| `GET /astronomy/conjunctions` | Close approaches, with timing uncertainty |
| `GET /astronomy/positions` | All bodies on one date |
| `GET /astronomy/catalogue` | Recorded comets, supernovae, meteor showers |
| `GET /astronomy/correlate` | Everything astronomical about a candidate date |
| `GET /astronomy/engine` | Models, accuracies and **stated limitations** |

`GET /astronomy/engine` is worth reading before trusting any figure: it lists what the
engine can and cannot do in its own words.

---

## Calendars

| Endpoint | Purpose |
| --- | --- |
| `GET /calendars` | The twelve systems, with epochs and caveats |
| `GET /calendars/convert` | `system`, `year`, `month`, `day` → every other system |
| `GET /calendars/convert/maya` | Long Count, with a selectable correlation constant |
| `GET /calendars/year-span` | The Gregorian span one year of another calendar covers |

`year-span` exists because most ancient dates are known only to the year, and a lunisolar
or wandering year does not align with a Gregorian one. Returning the span is the
difference between "1446 AH" meaning "2024" and it meaning "part of 2024 and part of
2025".

Every conversion carries `is_exact` and, when inexact, an `uncertainty_note` explaining
why.

---

## Corpus and metadata

| Endpoint | Purpose |
| --- | --- |
| `GET /corpus/sources` | Curated sources, with a disclosure that it is a demonstration set |
| `GET /corpus/sources/{slug}` | One source, its passages and scholarly notes |
| `GET /corpus/events` | Astronomical events attested in documents |
| `GET /corpus/claim-types` | **The claim-type vocabulary and how to render it** |
| `GET /corpus/pipeline` | The eight agents and the active AI provider |

Clients should fetch `/corpus/claim-types` rather than hard-coding the vocabulary.

---

## Search

### `POST /search`

```json
{ "query": "the moon turned to blood", "mode": "semantic", "scope": "all", "limit": 20 }
```

`mode`: `semantic`, `keyword` or `hybrid`. `scope`: `analyses`, `corpus` or `all`.

Results below a relevance floor are **withheld**, not shown with a low score — a poor
match presented as a source manufactures a citation that looks authoritative. When
nothing clears the floor, `note` says so.

Searching `analyses` is scoped to the caller. This is an authorisation boundary, not a
filter convenience.

`GET /search/history`, `DELETE /search/history`, `GET /search/corpus/stats` are also
available.

---

## Auth

| Endpoint | Purpose |
| --- | --- |
| `POST /auth/register` | Minimum 12 characters; length is weighted over composition |
| `POST /auth/login` | |
| `POST /auth/refresh` | A refresh token is **not** accepted as an access token |
| `POST /auth/logout` | |
| `GET /auth/me` | |
| `GET/PATCH /auth/me/settings` | |
| `GET /auth/oauth/providers` | Which providers are configured |
| `GET /auth/oauth/{provider}/authorize` | Google or GitHub |

OAuth returns tokens in the URL **fragment**, which browsers do not send to servers and
which stays out of referrer headers and access logs.

---

## Library

Projects, collections, tags, shares, notifications and a dashboard summary. All require
authentication.

`POST /analyses/{id}/share` returns a share token **once**. It is stored only as a keyed
hash and genuinely cannot be recovered — revoke and reissue instead.

---

## Admin

Requires the `admin` role (`/admin/audit` accepts `moderator`).

| Endpoint | Purpose |
| --- | --- |
| `GET /admin/users`, `PATCH /admin/users/{id}/role`, `.../active` | User management |
| `GET /admin/system` | Provider, corpus, job queue, stuck analyses |
| `GET /admin/usage` | Volume, durations, and the **evidence ratio** |
| `GET/POST /admin/prompts` | Versioned prompt overrides |
| `GET /admin/datasets`, `POST /admin/datasets/reseed` | Dataset management |
| `GET /admin/audit` | Append-only audit log |
| `GET /admin/jobs`, `POST /admin/jobs/{id}/retry` | Job queue |

The **evidence ratio** — the share of claims that are evidence-grade rather than
interpretation — is the number to watch. A falling ratio means the platform is producing
more conjecture relative to verifiable findings.

---

## Errors

```json
{
  "error": "validation_failed",
  "detail": "Some fields were not accepted.",
  "field_errors": { "text": ["The text is empty."] },
  "request_id": "29aaa7766fdb4d7d8611e647ab3c4184"
}
```

| Status | `error` | Meaning |
| --- | --- | --- |
| 400 | `bad_request` | Malformed input, unfetchable URL, unreadable file |
| 401 | `unauthenticated` | Missing or invalid token |
| 403 | `forbidden` | Authenticated but not permitted |
| 404 | `not_found` | Does not exist, **or** you may not read it |
| 409 | `conflict` | Already exists |
| 413 | `payload_too_large` | Over the upload limit |
| 422 | `validation_failed` | Field errors in `field_errors` |
| 429 | `rate_limited` | See `Retry-After` |
| 500 | `internal_error` | Quote the `request_id` when reporting |

Internal errors never include the exception text — stack traces leak schema and file
paths. The `request_id` is the bridge to the full log entry.

---

## Rate limits

| Caller | Default per hour |
| --- | --- |
| Anonymous | 10 |
| Authenticated | 120 |
| Moderator/admin | 1000 |

Every response carries `X-RateLimit-Limit`, `-Remaining` and `-Reset`; a 429 adds
`Retry-After`.

Limits are per bucket (`analyze`, `upload`, `search`, `export`, `auth`, `reference`), so
exhausting one does not block the others.
