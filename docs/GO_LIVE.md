# Going live on www.astro-decoded.com

This is the specific version of [DEPLOYMENT.md](DEPLOYMENT.md), written for one domain
with real values you can copy. Read the first section before buying or configuring
anything — it is the decision the rest depends on.

---

## First: what "hosting" you have matters, and most registrar hosting will not work

Starcode is not a website. It is four running things:

| Part | Needs |
| --- | --- |
| Web app | A **Node.js** runtime (Next.js server-rendering — not static files) |
| API | A **long-running Python 3.11 process** (FastAPI), always on |
| Database | **PostgreSQL with the `pgvector` extension** installed |
| Worker | A **second always-on Python process** that runs analyses in the background |

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

## Path 2 — keep the domain where it is, run the software on managed hosts

Your registrar keeps the domain and you add DNS records pointing at two services. Nothing
is installed anywhere.

### 1. The API, worker and database

`render.yaml` creates all three at once. In Render: **Blueprints → New Blueprint
Instance**, point it at this repository, and approve. You get the API, the background
worker, PostgreSQL and Redis, already wired together, with `SECRET_KEY` generated for you.

Leave **Blueprint Path** empty. The file is at the repository root, which is where Render
looks by default — and the field is case-sensitive, so a typed path is one capital letter
away from "not found".

Set **Branch** to whichever branch holds this work; Render offers the default branch
first and does not warn you if the blueprint only exists on another one.

Four things it cannot do for you, in order:

1. **Enable pgvector**, once, after the database exists. From the database's "Connect"
   tab, copy the PSQL command and run:

   ```bash
   psql "$DATABASE_URL" -c "CREATE EXTENSION IF NOT EXISTS vector;"
   ```

   Without it the app still works — retrieval falls back to an in-process scan and
   `/api/v1/health` says so — but that scan gets slower as the corpus grows.

2. **Set `CORS_ORIGINS` and `FRONTEND_BASE_URL`** on the API service, both to
   `https://www.astro-decoded.com`. The blueprint leaves them blank on purpose: a wrong
   value here is exactly the failure that looks like the whole site is broken.

3. **Add the custom domain** `api.astro-decoded.com` to the API service, then create the
   `CNAME` Render gives you at your registrar.

4. **Optionally set `ANTHROPIC_API_KEY`** on both the API and the worker.

Prefer Railway or Fly.io? Both work — create the same three services by hand from
`backend/Dockerfile`, with the worker's start command set to `python -m app.workers.runner`.
The image binds `$PORT` when the platform sets one, and the app rewrites a
platform-supplied `postgresql://` URL to the driver SQLAlchemy needs, so the connection
string can be pasted as given.

**The worker is not optional.** The API queues analyses and the worker runs them. Skip it
and every submission sits at "queued" forever — which looks like the site is broken, with
nothing in the API logs to say why.

### 2. The web app

Deploy the `frontend` directory to Vercel or Netlify.

Set **one** environment variable, and set it before the first build:

```
NEXT_PUBLIC_API_URL=https://api.astro-decoded.com
```

This one is compiled into the code that runs in the browser, so it must be present when
the site is *built*, not just when it runs. If you set it afterwards you must redeploy.
The build refuses to complete without it rather than silently shipping a site that points
at `localhost` — that check exists because it is the single most common way this goes
wrong.

Then add `www.astro-decoded.com` as a custom domain and create the `CNAME` at your
registrar (Vercel: `cname.vercel-dns.com`).

### 3. The apex

Point `astro-decoded.com` at the same frontend host and set a redirect to `www`. Vercel
and Netlify both do this from their dashboard. If your registrar offers "URL forwarding",
that works too.

### 4. Then

Check it and create your admin account exactly as in Path 1, steps 5 and 6 — for the
admin script, use your host's shell or one-off-command feature.

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
| The page loads, ANALYZE spins forever | The worker is not running. On Path 1: `docker compose ps` — the `worker` service should be up. On Path 2: you need that second service. |
| `redirect_uri_mismatch` on sign-in | The URI in the Google or GitHub console does not match the one above, character for character. |

`https://api.astro-decoded.com/api/v1/health` reports what the API thinks its own state
is — database, cache, corpus size, and whether it is running with an AI key or the
deterministic offline engine.

---

## What it costs, roughly

| | Path 1 | Path 2 |
| --- | --- | --- |
| Server | $6–12/mo VPS | Free tier to ~$20/mo |
| Database | included | included, or ~$7/mo |
| TLS | free | free |
| Domain | what you already pay | same |
| AI | only if you set `ANTHROPIC_API_KEY`, billed per analysis | same |

Without an Anthropic key the platform still runs: language detection, entity and date
extraction, calendar conversion and the whole astronomy engine are deterministic local
computation. The interpretive sections then report themselves as unavailable rather than
being filled with plausible-looking text — which is the same rule the rest of the platform
follows.
