# Deployment

Frontend on Vercel, backend on AWS, or both in containers anywhere. This covers the
configuration that actually bites.

---

## Before anything else

### Generate a real secret

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

The application **refuses to start** with `ENVIRONMENT=production` while `SECRET_KEY` is
the development sentinel, while `DEBUG` is true, or while `CORS_ORIGINS` is `*`. This is
deliberate — those are the three misconfigurations that turn a working deployment into an
open one.

### Get the three URLs consistent

This is the most common deployment failure, and it looks like a mysterious browser error
rather than a server one.

| Setting | Where | Must be |
| --- | --- | --- |
| `NEXT_PUBLIC_API_URL` | Frontend **build** | The public API URL |
| `CORS_ORIGINS` | Backend runtime | The public web URL |
| CSP `connect-src` | Frontend middleware (reads `NEXT_PUBLIC_API_URL`) | The public API URL |

`NEXT_PUBLIC_*` is compiled into the browser bundle at build time — changing it requires
a **rebuild**, not a restart. And `localhost` and `127.0.0.1` are different origins for
CORS and CSP purposes; pick one and use it everywhere.

Symptoms of getting this wrong:

- *"Refused to connect … violates Content Security Policy"* → `NEXT_PUBLIC_API_URL` at
  build time did not match the running value.
- *"blocked by CORS policy"* → the backend's `CORS_ORIGINS` does not list the web origin.

### The build now refuses to get this wrong

`next.config.mjs` validates `NEXT_PUBLIC_API_URL` at build time and **fails the build**
if it is missing, or if it points at `localhost` in a production build. That is
deliberate: the silent fallback used to bake `http://localhost:8000` into the bundle, and
the resulting failure appeared in the browser console as a CSP error, pointing at
entirely the wrong thing.

Set `NEXT_PUBLIC_ALLOW_LOCALHOST=true` for the one legitimate case — building a
production bundle to run against a local API, which is what CI and the e2e suite do.

Plain `http://` is allowed but warns, because a browser on an HTTPS page blocks
mixed-content requests.

The check runs on `next build` only. `next start` and `next lint` load the same config
file and also report `NODE_ENV=production`, but neither compiles a bundle — by the time
the server starts, the value is already inside `.next`, so the runtime container does not
need the build argument. This matters for the Docker image, whose runtime stage
deliberately carries no `NEXT_PUBLIC_*` variables.

---

## Connecting a custom domain

> For a start-to-finish walkthrough with real values rather than `example.com`, see
> [GO_LIVE.md](GO_LIVE.md). It covers both the one-server route
> (`deploy/docker-compose.prod.yml`, automatic TLS) and the split managed-host route.

A domain is the last step, not the first: it points at something that is already running.
For this platform that means **two** hosts, because the frontend and the backend have
genuinely different requirements.

| Host | Runs | Needs |
| --- | --- | --- |
| Frontend | Next.js | Any Node host or edge platform |
| Backend | FastAPI + worker | A long-running process, PostgreSQL with pgvector, and durable file storage |

Vercel cannot host the backend: it needs a persistent process for the job worker and a
Postgres database with an extension. Use Railway, Render, Fly.io or AWS for that half.

### The usual arrangement

```
example.com          → frontend    (A / CNAME to your frontend host)
api.example.com      → backend     (A / CNAME to your backend host)
```

### The four values that must agree

Changing to a real domain means changing all of these together. Miss one and the site
loads but every request fails.

| Value | Where it is set | Set it to |
| --- | --- | --- |
| `NEXT_PUBLIC_API_URL` | Frontend **build** | `https://api.example.com` |
| `CORS_ORIGINS` | Backend runtime | `https://example.com` |
| `FRONTEND_BASE_URL` | Backend runtime | `https://example.com` |
| `OAUTH_REDIRECT_BASE` | Backend runtime | `https://api.example.com` |

Then, in your OAuth provider's console, add the redirect URI:

```
https://api.example.com/api/v1/auth/oauth/google/callback
https://api.example.com/api/v1/auth/oauth/github/callback
```

### Checking it worked

```bash
curl -sI https://api.example.com/api/v1/health | head -1
curl -s https://api.example.com/api/v1/health | python3 -m json.tool

# The browser's view: this must return your frontend origin, not an error
curl -sI -X OPTIONS https://api.example.com/api/v1/analyses \
  -H "Origin: https://example.com" \
  -H "Access-Control-Request-Method: POST" | grep -i access-control-allow-origin
```

Then load the site and submit a short text. If the report renders, all four values agree.

### If it does not work

| Symptom (browser console) | Cause |
| --- | --- |
| `Refused to connect … Content Security Policy` | The frontend was built with a different `NEXT_PUBLIC_API_URL` than it is calling. Rebuild. |
| `blocked by CORS policy` | `CORS_ORIGINS` does not list the exact frontend origin |
| `Mixed Content: … was loaded over HTTPS, but requested an insecure resource` | `NEXT_PUBLIC_API_URL` is `http://` |
| Share links point at the wrong host | `FRONTEND_BASE_URL` is stale |
| OAuth returns `redirect_uri_mismatch` | `OAUTH_REDIRECT_BASE`, or the provider console, is stale |

`https://example.com` and `https://www.example.com` are **different origins**. Pick a
canonical one, redirect the other to it, and list only the canonical one in
`CORS_ORIGINS`.

### TLS

Vercel, Railway, Render and Fly issue and renew certificates automatically once the DNS
record resolves. On AWS, request an ACM certificate for `example.com` and
`api.example.com`, validate by DNS, and attach it to the load balancer.

HSTS is sent automatically when `ENVIRONMENT=production`. It is a one-way door for the
duration of its `max-age` — do not enable it until TLS is working on every hostname you
serve.

---

## Frontend on Vercel

```bash
cd frontend
vercel link
vercel env add NEXT_PUBLIC_API_URL production   # https://api.yourdomain.com
vercel --prod
```

Or connect the repository in the Vercel dashboard with **Root Directory** set to
`frontend`. Framework detection, build command and output directory are all automatic.

### What to know

**Middleware runs on the Edge runtime.** `middleware.ts` mints the CSP nonce per request.
It reads `NEXT_PUBLIC_API_URL` at runtime, so set it as a Vercel environment variable, not
only as a build arg.

**Pages render on demand.** Reading a per-request nonce means no static prerendering. For
this app that is close to free — every page that matters is client-driven — but it does
mean cold starts apply to the marketing pages too.

**Preview deployments need their own CORS entry.** Vercel gives each preview a unique
hostname. Either add a wildcard for your preview domain to `CORS_ORIGINS`, or point
previews at a staging API.

### Alternatives

Any Node host works. Netlify, Cloudflare Pages and Render all run the standard Next.js
build. For a container:

```bash
docker build --build-arg NEXT_PUBLIC_API_URL=https://api.yourdomain.com -t starcode-web ./frontend
```

---

## Backend on AWS

The backend is a container. Anything that runs one will do; ECS Fargate is the least
operationally involved.

### Suggested shape

```
Route 53 → ALB (TLS) → ECS Fargate
                        ├── api service     (2+ tasks)
                        └── worker service  (1+ tasks)
                              │
                        RDS PostgreSQL 16 + pgvector
                        ElastiCache Redis
                        S3 (uploads)
                        Secrets Manager
```

### Database

RDS PostgreSQL 16. Enable pgvector once:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

The migration creates it too, if the connecting role has permission. Grant that
permission or run it manually as a superuser; on RDS, `rds_superuser` suffices.

Sizing: `db.t4g.medium` is comfortable for early production. The tables are text-heavy;
watch `analyses`, `claims` and `knowledge_chunks`.

### Secrets

Never in a task definition. Reference Secrets Manager:

```json
{
  "secrets": [
    { "name": "SECRET_KEY",        "valueFrom": "arn:aws:secretsmanager:...:starcode/secret-key" },
    { "name": "DATABASE_URL",      "valueFrom": "arn:aws:secretsmanager:...:starcode/database-url" },
    { "name": "ANTHROPIC_API_KEY", "valueFrom": "arn:aws:secretsmanager:...:starcode/anthropic-key" }
  ]
}
```

The application logger redacts anything whose key looks like a credential, but the right
control is not putting them in the environment listing in the first place.

### Migrations

The container entrypoint runs `alembic upgrade head` before serving, so a rolling deploy
never has a process talking to a schema it does not expect.

For a large migration, run it as a one-off task first and deploy after it completes:

```bash
aws ecs run-task --cluster starcode --task-definition starcode-api \
  --overrides '{"containerOverrides":[{"name":"api","command":["alembic","upgrade","head"]}]}'
```

Set `SEED_ON_START=false` on the worker service so only one task seeds.

### Uploads

The default writes to a container-local directory, which is ephemeral. For production
either mount EFS at `UPLOAD_DIR` or use S3.

Uploads are content-addressed under a SHA-256 path, so the storage layout is
collision-free and a user's filename never touches a path.

### Health checks

| Path | Use |
| --- | --- |
| `/api/v1/health/live` | Liveness — touches no dependency |
| `/api/v1/health/ready` | Readiness — 503 if the database is unreachable |
| `/api/v1/health` | Full detail, for humans and monitoring |

Point the ALB target group at `/api/v1/health/ready`. Using the full check would take an
instance out of service for a degraded Redis, which is survivable.

### Scaling

The API is stateless — scale on CPU or request count.

The worker scales independently. Jobs are claimed with a conditional `UPDATE`, so two
workers racing for the same row cannot both run it, and a stale sweep returns work
abandoned by a dead worker. Add worker tasks when the `jobs` table shows a growing pending
count (`GET /admin/system`).

**Rate limiting needs Redis when you have more than one API task.** Without it, limits
fall back to per-worker counters, which multiplies the effective limit by the task count.
`/api/v1/health` reports which backend is active.

**OAuth sign-in currently requires a single API replica, or sticky sessions.** The
one-time `state` value that ties an authorization request to its callback is held in
process memory (`app/api/v1/routers/auth.py`). With several replicas behind a round-robin
load balancer, a callback that lands on a different replica than the one that issued the
state is rejected as a forgery, and the user sees a failed sign-in on roughly
`1 − 1/replicas` of attempts.

Until that state moves to Redis, pick one:

- run a single API task (perfectly reasonable at launch — the worker still scales
  independently, and anonymous analysis is unaffected);
- enable session affinity on the load balancer for `/api/v1/auth/oauth/*`;
- or run OAuth-free and create accounts with `scripts/create_admin.py`.

Anonymous analysis, the homepage, and all analysis endpoints scale horizontally without
any of this — only the OAuth handshake is affected.

---

## Accounts

`ALLOW_PASSWORD_REGISTRATION` is `false` by default and `POST /auth/register` answers
`403` while it is. There is no password-reset flow, and an account nobody can recover is
worse than no account: the person who forgets the password loses their saved analyses
permanently.

This is not a limitation you need to work around before launching. The homepage works
with no account at all, and OAuth both creates the account and verifies the address in one
step. Configure `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` or the GitHub pair and sign-in
works.

Set `ALLOW_PASSWORD_REGISTRATION=true` only once you have built a reset flow. Existing
password accounts — including an admin created with `scripts/create_admin.py` — can always
sign in regardless of the setting, so the default never locks an operator out.

The frontend reads `GET /auth/oauth/providers` and hides the registration form when the
server says it is unavailable, rather than offering a form the API refuses.

---

## Environment reference

### Required in production

| Variable | Notes |
| --- | --- |
| `ENVIRONMENT` | `production` — enables the startup checks |
| `SECRET_KEY` | A real generated secret |
| `DATABASE_URL` | `postgresql+psycopg://…` |
| `CORS_ORIGINS` | Exact web origins, comma-separated. Never `*` |
| `FRONTEND_BASE_URL` | Used to build share links |
| `OAUTH_REDIRECT_BASE` | The public API URL |

### Strongly recommended

| Variable | Why |
| --- | --- |
| `REDIS_URL` | Rate limits that hold across replicas |
| `ANTHROPIC_API_KEY` | Without it the interpretive sections report as unavailable |
| `TRUSTED_HOSTS` | Host-header validation |
| `UPLOAD_DIR` | Durable storage |
| `LOG_FORMAT=json` | Structured logs for aggregation |

### Worth tuning

`RATE_LIMIT_ANONYMOUS_PER_HOUR` (10), `RATE_LIMIT_USER_PER_HOUR` (120),
`MAX_UPLOAD_BYTES` (25 MB), `MAX_TEXT_CHARS` (400,000), `AI_MAX_RETRIES` (3),
`AI_TIMEOUT_SECONDS` (120), `OCR_LANGUAGES` (`eng`),
`AI_HYPOTHESIS_CONFIDENCE_CAP` (0.55).

That last one is a product policy, not a performance knob. Raising it lets the model
express more confidence in its own conjecture; think carefully before you do.

---

## CI/CD

`.github/workflows/ci.yml` runs on every push and pull request:

| Job | Checks |
| --- | --- |
| `backend` | ruff lint, format, mypy, 271 tests with coverage |
| `migrations` | Upgrade, seed, **downgrade and back up**, and `alembic check` against real PostgreSQL |
| `frontend` | lint, typecheck, unit tests, production build |
| `e2e` | 19 end-to-end + 16 accessibility tests against the real stack |
| `security` | pip-audit, npm audit, committed-credential scan |
| `docker` | Both images build; the API image boots and answers |

The `alembic check` step catches a model changed without a matching migration, which
otherwise surfaces as a runtime error in production. The downgrade step exists because a
migration you cannot reverse is a migration you cannot roll back.

### Adding deployment

Append a job gated on the others:

```yaml
  deploy:
    needs: [backend, frontend, e2e, migrations, security, docker]
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    environment: production        # use a protection rule for manual approval
    steps:
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_DEPLOY_ROLE }}   # OIDC, not long-lived keys
          aws-region: eu-west-1
      - run: |
          aws ecs update-service --cluster starcode --service api    --force-new-deployment
          aws ecs update-service --cluster starcode --service worker --force-new-deployment
```

Use OIDC role assumption rather than stored access keys.

---

## Operating it

### What to watch

| Signal | Where | Concerning when |
| --- | --- | --- |
| Pending jobs | `GET /admin/system` | Growing steadily — add workers |
| Stuck analyses | `GET /admin/system` | Non-zero — check for crash loops |
| Failed jobs | `GET /admin/jobs?status=failed` | Any sustained rate |
| **Evidence ratio** | `GET /admin/usage` | Falling — more conjecture per finding |
| Rate-limit backend | `GET /api/v1/health` | "in-process" with >1 replica |
| Corpus chunks | `GET /api/v1/health` | Zero — seeding did not run |

The evidence ratio is the product-health metric, not an infrastructure one. It tracks
what fraction of what the platform tells people is checkable.

### Logs

Structured JSON with a request id on every line, and credential-shaped keys redacted.
Correlate a user-facing error with its log entry via the `request_id` in the response
body.

### Backups

Automated RDS snapshots plus point-in-time recovery. Test a restore before you need one.

Uploads are re-derivable only if users still have the originals — back up `UPLOAD_DIR`
or the S3 bucket. The corpus is re-seedable from code at any time.

---

## Hardening checklist

- [ ] `SECRET_KEY` generated, in a secret store, not in an image or a task definition
- [ ] `ENVIRONMENT=production`
- [ ] `CORS_ORIGINS` lists exact origins, no wildcard
- [ ] `TRUSTED_HOSTS` set
- [ ] TLS terminated at the load balancer; HSTS is sent automatically in production
- [ ] Database not publicly reachable; TLS enforced
- [ ] Redis in a private subnet with auth enabled
- [ ] A proxy that **overwrites** `X-Forwarded-For` (otherwise per-IP limits are spoofable)
- [ ] Uploads on durable storage, not served back inline
- [ ] Audit log retention set to your policy
- [ ] At least one admin account, and no shared credentials
- [ ] Alarms on 5xx rate, job failure rate and database CPU

---

## Rollback

**Application:** redeploy the previous image tag. The API is stateless.

**Database:** `alembic downgrade -1`. The initial migration is reversible and CI proves
it on every run. Before doing this in production, confirm the specific migration is
reversible without data loss — dropping a column loses what was in it, whatever Alembic
reports.

**Frontend:** Vercel keeps every deployment; promote a previous one.
