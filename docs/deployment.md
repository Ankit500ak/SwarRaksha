# SwarRaksha — Deployment Guide

Production-shaped deployment per PLAN.md §10:

| Piece | Where | Config in repo |
|---|---|---|
| API (+ ML detector + voiceprint, in-process) | Render, Docker service | `render.yaml`, `infra/docker/Dockerfile.api` |
| Web frontend (React + Vite) | Vercel | `apps/web/vercel.json` |
| Database | Managed Postgres (Render Postgres, or any provider) | `DATABASE_URL` |
| Full stack on one machine (alternative) | Docker Compose | `infra/docker/docker-compose.yml` |

**Why the API is one service, not three:** the API imports the ML and
voiceprint packages directly (`from ml_inference import ...`,
`from voiceprint import ...` in `apps/api/app/`). `Dockerfile.api` copies
all three packages into one image with `PYTHONPATH=/app`, so a single
Render service runs API + ML together. The ML package also ships a
standalone HTTP app (`ml_inference.app`, port 8001) — that is what the
`ml` service in docker-compose runs — but no separate Render service is
needed. Voiceprint has no HTTP app at all; it is a library.

**Honest status notes (read before go-live):**

- The detector is still `baseline-heuristic-v0` — an *untrained*
  heuristic — and speaker verification is the MFCC baseline. Deploying
  this stack does **not** make the models trained or benchmarked. See
  `services/ml-inference/MODEL_CARD.md`.
- Some env vars below are wired for production hardening but are **not
  yet read by the API code on `main`**: CORS is still allow-all
  (`allow_origins=["*"]` in `apps/api/app/main.py`), Redis is not yet
  used, SMTP delivery is not yet wired (`SWAR_DEV_MODE=1` currently just
  logs OTPs), and voiceprint embeddings are not yet encrypted at rest.
  Set the variables anyway — the hardening lanes read them — but do not
  claim those protections are live until the code lands.
- Docker is **not installed** on the dev VM this was written on. The
  compose file was validated with a Python YAML parse and manual review
  only — see [What remains unverified without Docker](#what-remains-unverified-without-docker).

---

## 1. Environment variables the operator must set

No real values belong in git. Set these in the Render / Vercel
dashboards (or in the repo-root `.env` for compose — copy
`.env.example`, never commit `.env`).

### API service (Render / compose)

| Variable | Required | Notes |
|---|---|---|
| `JWT_SECRET` | Yes | Long random value. Signs login tokens. |
| `DATABASE_URL` | Yes (Render) | SQLAlchemy form: `postgresql+psycopg://user:password@host:5432/dbname`. Render's raw connection string lacks `+psycopg` — add it. In compose it is built from the `POSTGRES_*` vars instead. |
| `POSTGRES_PASSWORD` | Yes (compose only) | Compose refuses to start without it (`:?` interpolation). Also `POSTGRES_USER` / `POSTGRES_DB` (default `swarraksha`). |
| `VOICEPRINT_ENC_KEY` | For production | Key for encrypting voiceprint embeddings at rest (PLAN.md §11). Placeholder until the encryption code lands — set it so rotation history starts clean. |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | For production | OTP email delivery. Without a working SMTP setup, production login cannot deliver codes (dev mode logging is local-only). |
| `CORS_ORIGINS` | For production | Comma-separated allowed web origins, e.g. the Vercel production domain. Until the API reads it, CORS stays allow-all — a known, tracked gap. |
| `SWAR_ENV` | Yes | Set to `production`. |
| `SWAR_DEV_MODE` | Yes | Must be `0` in production. `1` prints OTPs to the server log — local development only. |
| `VOICEPRINT_THRESHOLD` | No | Cosine threshold, default `0.80`. Starting value, uncalibrated (see MODEL_CARD). |
| `REDIS_URL` | Compose sets it | Sessions / stream state / rate limits (PLAN.md §5). The API does not read it yet. |

### Web (Vercel)

| Variable | Required | Notes |
|---|---|---|
| `VITE_API_URL` | Yes | Public base URL of the deployed API, e.g. `https://swarraksha-api.onrender.com`. It is **baked into the JS bundle at build time** — change it, then redeploy the web app. In compose it is a build arg with the same semantics. |

---

## 2. Render — API + managed Postgres

1. **Account owner action:** create a Render account and a payment
   method if using the `starter` plan (free web services spin down when
   idle and are demo-grade only).
2. Push this repo to GitHub, then in Render: **New → Blueprint**, select
   the repo. Render reads the root `render.yaml` and proposes the
   `swarraksha-api` Docker web service (health check `/health`) and the
   `swarraksha-db` Postgres database.
3. At blueprint creation, Render prompts for every `sync: false`
   variable. Fill them from the table above. For `DATABASE_URL`, take
   the new database's **internal** connection string and rewrite the
   scheme to `postgresql+psycopg://`.
4. Deploy. Watch the first build: it builds `infra/docker/Dockerfile.api`
   with the **repo root as Docker context** — if the context is set to a
   subdirectory, the `COPY services/...` lines fail by design.
5. Verify: `GET https://<your-service>.onrender.com/health` returns
   `{"status": "ok", ...}` and `dev_mode: false`.
6. **Account owner action:** Postgres free plans on Render expire after
   a trial window. Move the database to a paid plan before real users,
   and confirm daily backups are on (PLAN.md §10: daily backup, 7-day
   retention).

## 3. Vercel — web frontend

1. **Account owner action:** create a Vercel account.
2. **New Project → import the GitHub repo**, set **Root Directory** to
   `apps/web`. `apps/web/vercel.json` already sets the Vite framework,
   `npm run build`, `dist` output, and an SPA rewrite (all routes →
   `/index.html`, so privacy/terms deep links work).
3. Add the environment variable `VITE_API_URL` = the Render API URL
   (Production environment), then deploy.
4. Copy the production domain and set it as `CORS_ORIGINS` on the API
   service, then redeploy the API.
5. Verify: open the site, sign in with an OTP (requires working SMTP on
   the API — see the honest notes), run one clip check end-to-end.

## 4. Alternative — full stack with Docker Compose

On any host with Docker:

```bash
cp .env.example .env     # set POSTGRES_PASSWORD and JWT_SECRET at minimum
docker compose -f infra/docker/docker-compose.yml up -d --build
docker compose -f infra/docker/docker-compose.yml ps   # all healthy?
curl http://localhost:8000/health
# web on http://localhost:5173, ML service on http://localhost:8001 (localhost only)
```

Services: `db` (Postgres 16, named volume `pgdata`), `redis` (named
volume `redisdata`), `ml` (detector HTTP app), `api` (waits for healthy
db/redis/ml), `web` (nginx, waits for a healthy API). All restart
`unless-stopped`. Secrets come only from `.env`; there are no fallback
passwords in the file.

## 5. Go-live checklist

- [ ] `SWAR_ENV=production` and `SWAR_DEV_MODE=0` on the API
- [ ] `JWT_SECRET` is a fresh random value, set only in the host dashboard / `.env`
- [ ] `DATABASE_URL` uses `postgresql+psycopg://` and points at managed Postgres
- [ ] Postgres is on a non-expiring plan; daily backups confirmed
- [ ] SMTP credentials set and a real OTP email received in a test inbox
- [ ] `VITE_API_URL` on Vercel points at the production API; web redeployed after setting it
- [ ] `CORS_ORIGINS` set to the production web domain (and the API CORS code updated to read it — still open on `main`)
- [ ] `VOICEPRINT_ENC_KEY` set (and the at-rest encryption code landed — still open on `main`)
- [ ] `/health` green on the API; one full sign-in → enroll → clip-check flow passes on production URLs
- [ ] Privacy Policy and Terms pages reachable in the web app (footer links) and reviewed by the owner
- [ ] Custom domains + DNS configured, if used (owner action, below)

## 6. What only the account owner can do

These cannot be done from code or this repo:

- Create the **Render** and **Vercel** accounts and connect them to GitHub
- Add a **payment method** / choose paid plans (Render starter service, non-expiring Postgres)
- Create real **SMTP credentials** with an email provider and verify the sending domain (SPF/DKIM records in DNS)
- Buy/configure **custom domains** and DNS records (API + web), if wanted
- Fill in the **privacy contact / grievance officer details** shown in the app's Privacy Policy (currently a placeholder)
- Decide the data-retention and breach-notification process required by the DPDP Act before real families enroll

## 7. What remains unverified without Docker

Docker is not installed on the dev VM, so the following were **not**
run and must be checked on the first machine that has Docker:

- `docker compose -f infra/docker/docker-compose.yml config` (interpolation of the `:?` required-secret guards and the constructed `DATABASE_URL`)
- Image builds for `Dockerfile.api`, `apps/web/Dockerfile`, and `services/ml-inference/Dockerfile`
- Healthcheck commands inside the running containers (`pg_isready`, `redis-cli ping`, the Python `urllib` probes, nginx `wget`)
- The full `depends_on: service_healthy` startup ordering end-to-end

What *was* verified: the compose file parses as valid YAML (Python
`yaml.safe_load`), every service has a healthcheck + restart policy,
no fallback/default secrets remain in the file, and `Dockerfile.api`'s
copy layout was checked line-by-line against the API's actual imports.
