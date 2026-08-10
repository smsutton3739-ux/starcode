# Administrator guide

Running Starcode: accounts and roles, monitoring, the corpus, prompts, and the audit
trail.

All admin endpoints live under `/api/v1/admin` and require the `admin` role; the audit
log also accepts `moderator`. The web console is at `/admin`.

---

## Creating the first administrator

There is no bootstrap endpoint — an unauthenticated route that mints an admin is a
liability that outlives its usefulness. It is a script, run by someone with shell access
to the deployment:

```bash
# Local, from backend/, with the same environment the API uses
python3 scripts/create_admin.py --email you@example.com

# Docker
docker compose exec api python3 scripts/create_admin.py --email you@example.com
```

It prompts for the password without echoing it. For unattended provisioning, set
`STARCODE_ADMIN_PASSWORD` instead — never pass a password as a command-line argument,
where it is visible to every process on the host and saved to shell history.

This is the only way to get the first administrator, because password registration is
disabled by default (see [DEPLOYMENT.md](DEPLOYMENT.md#accounts)). Accounts created this
way sign in normally regardless of that setting.

Re-running it against an existing address changes that account's role and leaves the
password alone:

```bash
python3 scripts/create_admin.py --email colleague@example.com --role moderator
python3 scripts/create_admin.py --email you@example.com --reset-password   # locked out
```

After the first one, promote everyone else through the API or admin console, which records
the change in the audit log — the script does not.

---

## Roles

| Role | Can |
| --- | --- |
| `viewer` | Read shared analyses |
| `user` | Run and manage their own analyses (the default) |
| `researcher` | As `user`, with room for higher limits |
| `moderator` | Read any analysis; read the audit log |
| `admin` | Everything: users, prompts, datasets, system |

Roles are ordered, and checks are "at least this role", so adding a level between two
existing ones does not require touching every check.

Two guards you will meet:

- **You cannot remove your own admin role**, and cannot deactivate your own account. This
  is what stops a single administrator locking everyone out.
- **Moderators can read any analysis.** That is a real privacy power. Grant it
  deliberately, and note that every such read is audited.

```bash
curl -X PATCH "$API/admin/users/$USER_ID/role" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"role":"researcher"}'

curl -X PATCH "$API/admin/users/$USER_ID/active?active=false" \
  -H "Authorization: Bearer $TOKEN"
```

Deactivating blocks sign-in immediately but leaves the account and its data intact —
reversible, unlike deletion.

---

## Monitoring

### `GET /admin/system`

```json
{
  "environment": "production",
  "ai_provider": { "provider": "anthropic", "model": "claude-opus-5", "is_offline": false },
  "rate_limit_backend": "_RedisBackend",
  "corpus": { "total_chunks": 96, "vector_backend": "pgvector" },
  "jobs": { "pending": 2, "running": 1, "succeeded": 1841, "failed": 3 },
  "stuck_analyses": 0,
  "warnings": []
}
```

What to react to:

| Signal | Means | Do |
| --- | --- | --- |
| `is_offline: true` unexpectedly | The API key is missing or invalid | Check the secret; reports are running without interpretive sections |
| `rate_limit_backend` not Redis | Limits are per worker | Fix `REDIS_URL` — with N replicas your limits are N× higher than intended |
| `corpus.total_chunks: 0` | Seeding never ran | `POST /admin/datasets/reseed` |
| `stuck_analyses` > 0 | Workers died mid-analysis | Check worker logs; the stale sweep requeues them |
| `jobs.pending` climbing | Not enough worker capacity | Add worker tasks |

### `GET /admin/usage?days=30`

Volume, durations, source-kind mix, and the metric that matters most:

```json
{
  "analyses": 1204,
  "average_duration_ms": 18400,
  "by_claim_type": { "source_text": 3811, "astronomical_calculation": 2044, "ai_hypothesis": 5992, ... },
  "evidence_ratio": 0.41,
  "evidence_ratio_note": "The share of claims that are evidence-grade rather than interpretation…"
}
```

**The evidence ratio is the product-health metric.** It is the fraction of everything the
platform tells people that is checkable — quotation, calculation, or cited history.

Watch it over time rather than against a target. A ratio drifting down means the platform
is producing more conjecture per verifiable finding, which can come from a prompt change,
a model change, or simply a shift in what users are submitting. Any of those is worth
knowing about; none of them announce themselves.

If it falls sharply after a deploy, look at what changed in the prompts.

---

## Jobs

```bash
curl "$API/admin/jobs?status=failed" -H "Authorization: Bearer $TOKEN"
curl -X POST "$API/admin/jobs/$JOB_ID/retry" -H "Authorization: Bearer $TOKEN"
```

Jobs live in the database, so they survive restarts. A worker that dies mid-job leaves
the row in `running`; the stale sweep returns it to the queue after 30 minutes, or marks
it failed if it is out of retries — and in that case the analysis is marked failed with a
message telling the user resubmission usually works.

Sustained failures are almost always one of: the AI provider unreachable, the database
under pressure, or a specific document that breaks extraction. `last_error` on the job
says which.

---

## The corpus

### What it is

A curated demonstration corpus: about 14 historical sources and 17 passages spanning Near
Eastern, Mediterranean, South Asian, East Asian and Mesoamerican traditions, plus
astronomical catalogues. Everything in it is citable.

It is **not** a comprehensive scholarly database, and the API says so in its own
responses. That disclosure matters: without it, users read "no match found" as "this text
is unknown", which is a much stronger claim than the corpus can support.

### Reseeding

```bash
curl -X POST "$API/admin/datasets/reseed" -H "Authorization: Bearer $TOKEN"
```

Idempotent — existing rows are updated in place. Run it after deploying corpus changes or
if `total_chunks` is zero.

### Adding sources

The seed corpus lives in code (`backend/app/knowledge/corpus.py`) so that it is
reviewable, diffable and versioned alongside everything else. Adding entries there is a
code change and a deploy, not a database edit. See [DEVELOPER.md](DEVELOPER.md).

For material too large or too frequently updated for that — a licensed dataset, an
institutional export — use the JSON importer instead:

```bash
python3 scripts/import_dataset.py corpus.json --dry-run   # validate, change nothing
python3 scripts/import_dataset.py corpus.json
```

It validates the entire file before writing anything, so one bad entry imports nothing and
every problem is listed at once. It refuses sources without a citation, translations
without a credit, and events described as records that name no record. Those refusals are
the point: retrieved passages are cited in reports, and unprovenanced material would
quietly erode the labelling. Re-running the same file updates rather than duplicates, so
it is safe in a deploy script. The file format is documented at the top of the script.

The one field to insist on in review is `dating_note`. When a text was written determines
whether it could have preceded the events it appears to describe — the whole question for
prophetic material. It should record the actual scholarly disagreement, not a smoothed
single number.

### Enabling and disabling datasets

```bash
curl "$API/admin/datasets" -H "Authorization: Bearer $TOKEN"
curl -X PATCH "$API/admin/datasets/$ID?enabled=false" -H "Authorization: Bearer $TOKEN"
```

Each dataset records its provider, licence and record count — the honest answer to "where
did this claim come from?".

---

## Prompts

```bash
curl "$API/admin/prompts" -H "Authorization: Bearer $TOKEN"
```

Agents ship with built-in prompts. Stored overrides are versioned, and only one version
per agent is active, so an existing report can always be explained in terms of the prompt
that produced it.

```bash
curl -X POST "$API/admin/prompts?agent_name=interpretation&version=1.1.0&activate=true" \
  -H "Authorization: Bearer $TOKEN" \
  --data-urlencode "system_prompt=…"
```

### Before you edit a prompt

Every agent prompt inherits `SHARED_SYSTEM_RULES`, which carries the epistemic contract —
choose claim types honestly, do not invent citations, report disagreement, never assert a
future event.

**Do not remove those instructions.** The contract layer still enforces the hard rules
after generation, so removing them cannot make a fabricated citation *pass*. What it does
is waste generation: the model produces claims that get downgraded, and the report ends up
thinner and more hedged than it needed to be. The instructions and the enforcement work
together.

After any prompt change, run a few representative texts and check the evidence ratio.

---

## Audit log

Append-only. There is no update route and no delete route.

```bash
curl "$API/admin/audit?limit=50" -H "Authorization: Bearer $TOKEN"
curl "$API/admin/audit?action=login_failed" -H "Authorization: Bearer $TOKEN"
curl "$API/admin/audit?actor_id=$USER_ID" -H "Authorization: Bearer $TOKEN"
```

Recorded: sign-in and failures, registration, analysis creation/view/delete/export/share,
uploads accepted and rejected, URL fetches, role changes, deactivations, prompt and
dataset changes, rate limiting, and admin actions.

Design points worth knowing:

- **The actor's email is denormalised** onto the row, so the trail survives deletion of
  the account it describes.
- **IP addresses are hashed**, not stored raw — enough to correlate abuse across requests,
  not enough to identify a person.
- **Each entry carries the `request_id`**, so an audit row joins to the application logs.

Set a retention policy that matches your obligations; nothing prunes it automatically.

### What to look for

| Pattern | Suggests |
| --- | --- |
| Many `login_failed` from one hashed IP | Credential stuffing |
| Many `upload_rejected` from one actor | Probing the upload filter |
| `url_fetched` with unusual targets | SSRF probing (the fetcher blocks it, but the attempt is signal) |
| `role_changed` you did not expect | Investigate immediately |
| `rate_limited` sustained for one actor | Abuse, or a legitimate user who needs a higher limit |

---

## Privacy

Users submit texts that may be personal, unpublished, or sensitive.

- Analyses are private to their owner. Sharing is explicit, revocable and expirable.
- Anonymous analyses are reachable only via a token held in the user's browser. If they
  clear it, the analysis becomes unreachable — there is no recovery, by design.
- Moderators and admins **can** read any analysis. Every such read is audited.
- Exports are sent with `Cache-Control: private, no-store`.
- Deleting an analysis cascades to its claims, entities, references, reports and traces.

If you operate under GDPR or similar, note that a user's texts live in `documents` and
their analyses in `analyses`; deleting the user cascades both, while the audit trail
retains the denormalised email deliberately.

---

## Runbook

**"Reports have no interpretations."** Check `GET /admin/system` → `ai_provider`. If
`is_offline` is true the key is missing or invalid. This is a graceful degradation, not a
crash: extraction, calendars and astronomy still work.

**"Analyses are stuck at queued."** No worker is running, or all are wedged. Check
`GET /admin/jobs?status=pending` and the worker logs. Restart the worker service; jobs
survive restarts.

**"Users hitting rate limits."** Check `rate_limit_backend` first — if it is in-process
with multiple replicas, limits are inconsistent between them. Otherwise raise
`RATE_LIMIT_USER_PER_HOUR` or promote the users.

**"Search finds nothing."** Check `corpus.total_chunks`. If zero, reseed. If non-zero,
remember results below the relevance floor are withheld deliberately rather than shown
with a low score.

**"An upload was rejected."** The message says why. Files are identified by content, not
extension — HTML and script payloads are refused whatever they are named, which is
occasionally surprising for a `.txt` file containing markup.

**"An export is missing citations."** Only citations attached to claims appear.
Model-supplied ones are included but marked unverified; corpus-verified ones are listed
first.
