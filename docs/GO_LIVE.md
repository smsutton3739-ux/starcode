# Going live on www.astro-decoded.com

This is the specific version of [DEPLOYMENT.md](DEPLOYMENT.md), written for one domain
with real values you can copy. Read the first section before buying or configuring
anything — it is the decision the rest depends on.

---

## First: what "hosting" you have matters, and most registrar hosting will not work

Starcode is not a website. It is three running things:

| Part | Needs |
| --- | --- |
| Web app | A **Node.js** runtime (Next.js server-rendering — not static files) |
| API | A **long-running Python 3.11 process** (FastAPI), always on |
| Database | **PostgreSQL with the `pgvector` extension** installed |

A fourth, a dedicated worker process, is optional: the API runs each analysis on its own
thread, so a single service is a complete deployment. Split the worker out when analysis
volume starts competing with request handling.

The shared hosting that comes bundled with a domain — cPanel, "web hosting", the
one-click site builder — almost always provides PHP, MySQL and static file serving. None
of the four rows above. You can point the domain at a real host from your registrar in
about five minutes, and that is the normal arrangement: **the registrar keeps the domain,
someone else runs the servers.**

So before anything else, find out which of these your host is:

**A. It is a VPS / cloud server** — you get SSH and root on a Linux machine (Hetzner,
DigitalOcean, Linode, Vultr, OVH, a "cloud server" plan, AWS Lightsail). → **Path 1**,
below. Everything runs on that one box. About $6–12/month.

**B. It is shared hosting / cPanel / a site builder** — you get a file manager, PHP and
MySQL, maybe a "Node.js app" button. → **Path 2**. Keep the domain where it is, run the
software elsewhere, point DNS at it. The free tiers cover a launch.

**C. You are not sure.** Take Path 2. It works whichever of the two you turn out to have,
because your domain never moves either way — and if you are unsure what your hosting is,
you do not want to be administering a Linux server. A "Node.js selector" in cPanel can
sometimes run the web app, but it cannot give you PostgreSQL with pgvector, so Path 2
still applies to the API.

Either path ends with the same site at the same address. Path 1 is cheaper and keeps
everything in one place; Path 2 is less to operate and has nothing to patch.

---

## The names you will use

Whichever path, the site is split across two hostnames:

```
www.astro-decoded.com    the site people visit
api.astro-decoded.com    the API the site talks to
astro-decoded.com        redirects to www
```

`astro-decoded.com` and `www.astro-decoded.com` are **different origins** as far as
browsers are concerned — different for CORS, cookies and the Content-Security-Policy. One
of them has to be the real site. This guide makes it `www`, because that is what you
said, and redirects the bare domain to it.

---

## Path 1 — one server you control

### 1. Point the DNS at the server

At your registrar's DNS panel, with `203.0.113.10` replaced by your server's IP:

| Type | Name | Value |
| --- | --- | --- |
| A | `@` | `203.0.113.10` |
| A | `www` | `203.0.113.10` |
| A | `api` | `203.0.113.10` |

If your server has an IPv6 address, add the same three as `AAAA` records.

DNS takes anywhere from a minute to a few hours to propagate. Check with:

```bash
dig +short www.astro-decoded.com
dig +short api.astro-decoded.com
```

Both must print your server's IP before the next step, because the TLS certificates are
issued by proving control of those names.

### 2. Install Docker on the server

```bash
ssh root@203.0.113.10
curl -fsSL https://get.docker.com | sh
```

### 3. Get the code and configure it

```bash
git clone https://github.com/smsutton3739-ux/starcode.git
cd starcode
cp .env.example .env
```

Then edit `.env`. These are the values that matter — everything else can stay at its
default:

```bash
# The three hostnames
DOMAIN=www.astro-decoded.com
APEX_DOMAIN=astro-decoded.com
API_DOMAIN=api.astro-decoded.com
ACME_EMAIL=you@example.com          # where certificate-expiry warnings go

# Secrets. Generate, do not invent.
SECRET_KEY=                          # python3 -c "import secrets; print(secrets.token_urlsafe(48))"
POSTGRES_PASSWORD=                   # openssl rand -base64 24

# Optional but recommended
ANTHROPIC_API_KEY=                   # without it, the interpretive sections say so
                                     # rather than being filled with invented text
```

Generate the two secrets on the server and paste them in:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
openssl rand -base64 24
```

You do **not** need to set `CORS_ORIGINS`, `FRONTEND_BASE_URL`, `OAUTH_REDIRECT_BASE`,
`TRUSTED_HOSTS` or `NEXT_PUBLIC_API_URL` by hand. The production overlay derives all five
from `DOMAIN` and `API_DOMAIN`, which is the point: those five values must agree exactly,
and deriving them removes the most common way a deployment breaks.

### 4. Start it

```bash
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d --build
```

The first run takes a few minutes: it builds both images, starts PostgreSQL, applies the
database migrations, seeds the corpus, and obtains TLS certificates for all three
hostnames. Watch it with:

```bash
docker compose logs -f
```

Only ports 80 and 443 are published. The database, Redis, the API and the web app are
reachable only from inside the stack, so a misconfigured firewall cannot expose your
database.

### 5. Check it

```bash
curl -sI https://www.astro-decoded.com | head -1          # HTTP/2 200
curl -s https://api.astro-decoded.com/api/v1/health | python3 -m json.tool
curl -sI https://astro-decoded.com | head -2              # 301 to www
```

Then open https://www.astro-decoded.com, paste a few sentences of an ancient text, and
press ANALYZE. If the report renders, everything agrees.

### 6. Make yourself an administrator

```bash
docker compose exec api python3 scripts/create_admin.py --email you@example.com
```

It asks for a password without showing it. That account can reach `/admin`.

### Keeping it running

```bash
# Update to the latest code
git pull && docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d --build

# Back up the database (do this on a schedule — see DEPLOYMENT.md)
docker compose exec db pg_dump -U starcode starcode | gzip > backup-$(date +%F).sql.gz

# Logs
docker compose logs -f api
```

---

## Path 2 — free hosting, domain stays where it is

Three free accounts, nothing installed anywhere, no card required:

| Piece | Where | Free tier limit that matters |
| --- | --- | --- |
| Database | Supabase | Project pauses after 7 days with no queries |
| API | Render | Instance stops after ~15 min idle; next request waits ~1 min |
| Web app | Vercel | Generous; nothing you will hit |

Do them in this order. Each step needs a value from the one before it.

### 1. Supabase — the database

1. [supabase.com](https://supabase.com) → sign in with GitHub → **New project**.
2. Name it `starcode`. Choose the region closest to you. **Set a database password and
   save it somewhere** — it is shown once and you need it in step 4.
3. Wait about two minutes for provisioning.
4. **SQL Editor** (left sidebar) → **New query** → paste and **Run**:

   ```sql
   create extension if not exists vector;
   ```

   This is what makes semantic search use the database rather than an in-process scan.
   Without it the app still works and `/api/v1/health` says so, but the scan slows as the
   corpus grows.

5. **Connect** (top of the page) → the **Session pooler** tab → copy the URI.

   **Take the session pooler string, not "Direct connection".** The direct address is
   IPv6-only and Render cannot reach it; the failure is a connection timeout that says
   nothing about addressing.

   Replace `[YOUR-PASSWORD]` in that string with the password from step 2. Keep the whole
   thing — you paste it as `DATABASE_URL` next.

   It will start `postgresql://`. Paste it exactly as Supabase gives it; the app rewrites
   the prefix to the driver SQLAlchemy needs.

### 2. Render — the API

1. [render.com](https://render.com) → sign in with GitHub → **Blueprints** → **New
   Blueprint Instance**.
2. Connect `smsutton3739-ux/starcode`.
3. **Branch**: the branch holding this work. Render offers the default branch first and
   does not warn you when the blueprint is only on another one.
4. **Blueprint Path**: leave **empty**. `render.yaml` is at the repository root, where
   Render looks by default. The field is case-sensitive, so anything typed is one capital
   letter from "blueprint not found".
5. **Apply**. Render prompts for the three values the blueprint deliberately leaves
   unset:

   | Prompt | Paste |
   | --- | --- |
   | `DATABASE_URL` | The session pooler URI from step 1.5, password filled in |
   | `CORS_ORIGINS` | `https://www.astro-decoded.com` |
   | `FRONTEND_BASE_URL` | `https://www.astro-decoded.com` |

   Getting `CORS_ORIGINS` wrong is the failure that looks like the whole site is broken.
   Exact scheme, exact host, no trailing slash.

6. First build takes 5–10 minutes: the image installs Tesseract so scanned manuscripts
   can be read. Slow is normal here, not stuck.
7. When it is live, **Settings → Custom Domains → Add** `api.astro-decoded.com`. Render
   gives you a `CNAME` value — create that record at your registrar.

Everything else the API needs is already in the blueprint, including a generated
`SECRET_KEY` you never see or store.

### 3. Vercel — the web app

1. [vercel.com](https://vercel.com) → sign in with GitHub → **Add New → Project** →
   import `smsutton3739-ux/starcode`.
2. **Root Directory**: click **Edit** and set it to `frontend`. This is the one setting
   people miss; without it Vercel tries to build the repository root and fails.
3. **Framework Preset**: confirm it says **Next.js**, not **Other**. `frontend/vercel.json`
   pins it, so a fresh import should get this right on its own — but check, because the
   failure it causes does not look like a settings problem. On **Other**, Vercel still runs
   `next build` and reports a green build, then deploys none of it: no page functions, no
   `_next/static` assets, and `middleware.ts` picked up by Vercel's framework-agnostic
   Routing Middleware builder instead of Next's. Every request 500s with
   `MIDDLEWARE_INVOCATION_FAILED` and the runtime log blames `/var/task/frontend/middleware.js`,
   a path Next.js never emits. To check a live deployment, request any hashed chunk from
   its build log — `/_next/static/chunks/<name>.js`. A 404 there means the preset is wrong.
4. **Environment Variables** — add one, *before the first build*:

   ```
   NEXT_PUBLIC_API_URL = https://api.astro-decoded.com
   ```

   It is compiled into the code that runs in the browser, so it must exist at build time.
   Set it afterwards and you must redeploy. The build refuses to finish without it rather
   than shipping a site quietly pointed at `localhost`.

5. **Deploy**.
6. **Settings → Domains** → add `www.astro-decoded.com`, and add `astro-decoded.com` set
   to redirect to it. Create the DNS records Vercel shows you at your registrar.

### 4. Make yourself an administrator

Render's free tier has no shell, so `scripts/create_admin.py` is out of reach. Bootstrap
through the database instead — three steps, then you close the door again:

1. Render → your service → **Environment** → add `ALLOW_PASSWORD_REGISTRATION` = `true`.
   Save; the service redeploys.
2. Go to `https://www.astro-decoded.com/login`, click **Create one**, and register with
   your email and a long password.
3. Supabase → **SQL Editor** → run, with your address:

   ```sql
   update users set role = 'admin' where email = 'you@example.com';
   ```

4. Back in Render, set `ALLOW_PASSWORD_REGISTRATION` to `false` again.

Your account keeps working — the setting governs new registrations, not existing
accounts. If you would rather not open registration even briefly, configure Google or
GitHub sign-in first (see [Sign-in](#sign-in)), sign in that way, and run only step 3.

### What "free" actually costs you

**The API sleeps.** After ~15 minutes without traffic Render stops the instance, and the
next visitor waits up to a minute for the first page. It is genuinely free rather than
free-with-an-asterisk, and $7/month removes it whenever you want.

An analysis interrupted by that sleep is recovered rather than lost: the API sweeps for
abandoned work when it starts and periodically after, and requeues anything a stopped
process left behind.

**Supabase pauses after 7 days of no queries.** You restore it from the dashboard in a
click, but a site nobody visits for a week is down until you do. Visiting your own site
occasionally is enough to prevent it.

**No background worker and no Redis, on purpose.** Render's free tier has no worker
service — but the API runs each analysis on its own thread, so it does not need one. Add
a worker when analysis volume starts competing with request handling, not before. Redis
is likewise unnecessary on a single instance: rate limits are counted in-process, which
on one instance is not an approximation but exact.

### Running without an AI key

The blueprint sets `AI_PROVIDER=offline`, so the platform runs its deterministic engine
and nothing calls a paid API.

What still works, fully: language and script detection, entity and date extraction,
calendar conversion across all twelve systems, the entire astronomy engine — eclipses,
moon phases, planetary positions, conjunctions — corpus retrieval, citations, the report,
and every export format.

What does not: the interpretive sections. They report themselves as unavailable rather
than being filled with generated text. That is the same rule the platform applies
everywhere — the absence of evidence is stated, not papered over.

To switch it on later, add `ANTHROPIC_API_KEY` in Render's **Environment** tab and change
`AI_PROVIDER` to `auto`. Both take effect on the redeploy that follows. Leaving
`AI_PROVIDER=offline` while adding a key does nothing, which is the intended behaviour of
naming the mode explicitly.

### Deploying elsewhere

Railway and Fly.io work the same way: one service built from `backend/Dockerfile`. The
image binds `$PORT` when the platform sets one, and the app rewrites a platform-supplied
`postgresql://` URL to the driver SQLAlchemy needs, so the connection string can be
pasted as given.

---

## Sign-in

There are no passwords to create, by design: there is no password-reset flow, and an
account nobody can recover is worse than no account. People sign in with Google or GitHub,
or use the site with no account at all — which is the main path, and needs no
configuration.

To switch sign-in on:

**Google** — in the [Google Cloud console](https://console.cloud.google.com/apis/credentials),
create an OAuth 2.0 Client ID of type "Web application" and add this authorised redirect
URI, exactly:

```
https://api.astro-decoded.com/api/v1/auth/oauth/google/callback
```

**GitHub** — in Settings → Developer settings → OAuth Apps, create an app with:

- Homepage URL: `https://www.astro-decoded.com`
- Authorization callback URL: `https://api.astro-decoded.com/api/v1/auth/oauth/github/callback`

Then set `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` and/or `GITHUB_CLIENT_ID` /
`GITHUB_CLIENT_SECRET` on the API and restart it. The sign-in page picks them up on its
own — it asks the API what it supports rather than assuming.

One constraint while you have OAuth on: **run a single API instance.** The one-time value
that ties a sign-in request to its callback is held in that process's memory, so with two
instances behind a load balancer roughly half of all sign-ins fail. Path 1 is a single
instance already. On Path 2, leave the API at one instance until this moves to Redis. It
does not affect anonymous analysis, which is the main path and scales freely.

---

## Subscriptions

Optional. With none of the three Stripe values set, the platform runs exactly as
documented everywhere else: every account is on the free tier, checkout refuses with a
message naming the missing setting, and the webhook refuses every request rather than
trusting unsigned input.

### 1. Create the product and price

In the Stripe dashboard, **Product catalogue → Add product**. Give it a recurring price.
Copy the **price** id — it begins `price_`. The product id (`prod_`) is not what the
application needs and will fail at checkout.

### 2. Register the webhook endpoint

**Developers → Webhooks → Add endpoint.** The URL is your API's public address plus the
API prefix:

```
https://api.astro-decoded.com/api/v1/billing/webhook
```

The `/api/v1` is not optional. Every router in this application is mounted under
`API_V1_PREFIX`, so an endpoint registered at `/v1/billing/webhook` or
`/billing/webhook` returns 404 for every delivery — and because Stripe treats a 404 as a
delivery failure and retries, the symptom is a growing queue of failed events rather than
an obvious error.

Subscribe it to these four events. Everything else is ignored:

| Event | What it does here |
| --- | --- |
| `checkout.session.completed` | Grants the paid tier as soon as payment completes |
| `customer.subscription.updated` | Follows the subscription's status |
| `customer.subscription.deleted` | Returns the account to free |
| `invoice.payment_failed` | Records `past_due` without cutting access |

Stripe shows the **signing secret** once, when the endpoint is created. That is
`STRIPE_WEBHOOK_SECRET`.

### 3. Set the three values on Render

**Environment → Add environment variable**, on the API service:

| Variable | Where it comes from |
| --- | --- |
| `STRIPE_SECRET_KEY` | Developers → API keys → Secret key |
| `STRIPE_WEBHOOK_SECRET` | Shown once when the endpoint above was created |
| `STRIPE_PRICE_ID_PAID` | The recurring price on your product (`price_…`) |

All three are declared `sync: false` in `render.yaml`. Do not remove that — a synced
secret is overwritten with an empty value on the next Blueprint sync, and the first
symptom is every webhook failing signature verification with nothing in the diff to
explain it.

### 4. Check it end to end

Stripe's dashboard has a **Send test webhook** button on the endpoint. A correctly
configured deployment answers `200 {"received": true}`. The two failures worth
recognising:

- **400 `Stripe signature verification failed`** — `STRIPE_WEBHOOK_SECRET` does not match
  this endpoint. Each endpoint has its own secret; copying one from a different endpoint
  produces exactly this.
- **503 `STRIPE_WEBHOOK_SECRET is not set`** — the variable never reached the service.
  Check it is set on the API service rather than the web app.

### What paying changes, and what it does not

A subscription reveals the interpretive claim types — `traditional_interpretation`,
`scholarly_interpretation` and `ai_hypothesis` — plus the executive summary that draws on
them. It changes nothing about how those claims are labelled or how confident they are
allowed to be: an AI hypothesis is still capped by policy and still marked as not
evidence, on every plan.

Free readers see a locked placeholder in place of each withheld claim, keeping its type,
confidence and citations. That is deliberate: a report that silently omitted them would
misrepresent what the analysis actually found.

---

## The chart tools page

`/tools` embeds third-party birth-chart and synastry calculators from Astro·Charts. It is
off until you set your affiliate identifier:

```
NEXT_PUBLIC_ASTRO_CHARTS_AFF=your-affiliate-id
```

Build time, like every `NEXT_PUBLIC_*` value — on Path 1 the compose overlay passes it as
a build argument, so a rebuild picks it up:

```bash
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d --build web
```

Without it the page renders and explains that the tools are not configured, rather than
embedding a widget that credits nobody.

Two things about it are deliberate and worth keeping. The widgets live on their own page
rather than inside analysis reports, because a birth chart is astrology and a report is
supposed to be the place where interpretation is never presented as a finding. And the
permission to frame that origin is granted on `/tools` alone: a third-party script has
full access to whatever page it runs on, and the other pages can be holding someone's
submitted text and saved analyses. Tests in `tests/e2e/analysis.spec.ts` assert both
halves of that, so widening it by accident fails the build.

The page carries an affiliate disclosure. Keep it — in the US the FTC requires that a
material connection be disclosed clearly, and it is also simply what a reader is owed.

---

## If something is wrong

Open the browser's developer console (F12) on https://www.astro-decoded.com and read the
first error.

| What it says | What is wrong |
| --- | --- |
| `Refused to connect … Content Security Policy` | The frontend was built with a different `NEXT_PUBLIC_API_URL` than it is calling. Rebuild it with the right value. |
| `blocked by CORS policy` | `CORS_ORIGINS` on the API is not exactly `https://www.astro-decoded.com`. A trailing slash or a missing `www` is enough to break it. |
| `Mixed Content` | `NEXT_PUBLIC_API_URL` is `http://` where it should be `https://`. |
| Nothing loads at all | DNS has not propagated, or the certificate has not been issued yet. Check `dig +short www.astro-decoded.com` and `docker compose logs caddy`. |
| The page loads, ANALYZE spins forever | On Path 1, check `docker compose ps` — the `worker` service should be up. On Path 2 the API runs analyses itself, so this is usually the free instance having just woken: give it a minute and resubmit. |
| `connection to server ... failed` in the Render logs | `DATABASE_URL` is Supabase's *direct* connection, which is IPv6-only. Use the **Session pooler** string instead. |
| `password authentication failed` | `[YOUR-PASSWORD]` is still literally in `DATABASE_URL`, or the password contains characters that need URL-encoding. |
| `redirect_uri_mismatch` on sign-in | The URI in the Google or GitHub console does not match the one above, character for character. |

`https://api.astro-decoded.com/api/v1/health` reports what the API thinks its own state
is — database, cache, corpus size, and whether it is running with an AI key or the
deterministic offline engine.

---

## What it costs, roughly

| | Path 1 | Path 2 as documented |
| --- | --- | --- |
| Server | $6–12/mo VPS | **$0** — Render free |
| Database | included | **$0** — Supabase free |
| Web app | included | **$0** — Vercel free |
| TLS | free | free |
| Domain | what you already pay | same |
| AI | only if you set `ANTHROPIC_API_KEY`, billed per analysis | same |

Path 2 costs nothing beyond the domain you already own. The two things you buy by paying
later: $7/month on Render stops the API sleeping between visitors, and a Supabase paid
plan stops the database pausing after a quiet week. Neither is needed to launch.

Without an Anthropic key the platform still runs: language detection, entity and date
extraction, calendar conversion and the whole astronomy engine are deterministic local
computation. The interpretive sections then report themselves as unavailable rather than
being filled with plausible-looking text — which is the same rule the rest of the platform
follows.
