# Telegram Marketing CRM

A self-hosted, multi-user Telegram marketing CRM for reaching **consented contacts** and
managing **company-owned** channels/groups. See
[`Telegram_Marketing_CRM_Structure.md`](./Telegram_Marketing_CRM_Structure.md) for the full
specification, database schema, anti-ban design, and phased build plan.

> **Use policy:** internal company use only, targeting contacts who have given consent.
> Opt-outs are honored automatically and permanently.

---

## Stack

| Layer | Technology |
|---|---|
| Backend API | Python 3.11 · FastAPI |
| Telegram userbot | Telethon *(Phase 2+)* |
| Telegram bot | aiogram v3 *(Phase 10)* |
| Worker / scheduler | Celery + Redis |
| Database | PostgreSQL 15 |
| Cache / broker / pub-sub | Redis |
| Frontend | React + Vite + TypeScript |
| Reverse proxy / TLS | Caddy |
| Packaging | Docker + Docker Compose |

## Repository layout

```
Telegram_Marketing_CRM/
├── docker-compose.yml          # dev stack
├── docker-compose.prod.yml     # production overrides
├── .env.example                # configuration template
├── Caddyfile                   # reverse proxy / TLS
├── backend/                    # FastAPI app + engine + Celery worker
│   ├── app/                    # API, config, db, auth, schemas, services
│   ├── engine/                 # Telegram Engine Service (owns all sessions)
│   ├── worker/                 # Celery app + tasks
│   └── tests/
├── frontend/                   # React + Vite + TypeScript UI
└── sessions/                   # Telethon session files (gitignored volume)
```

## Quick start (Docker)

```bash
cp .env.example .env            # then edit secrets
docker compose up --build
```

- App (via Caddy): http://localhost
- API health check: http://localhost/health
- Backend direct: http://localhost:8000/health
- Frontend direct: http://localhost:5173

Production (HTTPS, hardened, nightly backups) — see the full
[**Deployment & Operations Guide**](./docs/DEPLOY.md) for Ubuntu VPS and Windows:

```bash
# set ENVIRONMENT=production, a strong SECRET_KEY, real admin/DB passwords,
# CORS_ORIGINS, and CADDY_SITE_ADDRESS=your-domain.com in .env first
docker compose run --rm backend python -m app.cli generate-secret   # strong SECRET_KEY
docker compose run --rm backend python -m app.cli prod-check         # verify no insecure defaults
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Caddy issues HTTPS automatically once your domain points at the server. In
production the backend **refuses to start** on default secrets, the API is
**rate-limited** per IP (tighter on login) and sends **security headers**, and a
`backup` service takes **nightly `pg_dump`** snapshots into `./backups`.

## Local development without Docker

Backend:

```bash
cd backend
python -m venv .venv
# Windows:  .venv\Scripts\activate    |    Unix:  source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

> A running PostgreSQL and Redis are only required from **Phase 1** onward. The `/health`
> endpoint has no external dependencies and works standalone.

## Build progress

Progress is tracked in the spec's **§13 Build Progress Tracker** and **§14 Activity Log**.
Current status: **all 13 phases (0–12) complete and deployed.** Phase 11 added the live
system-monitoring Dashboard, marketing analytics (funnel, per-source conversion,
campaign/A-B, UTM attribution), and the referral program; Phase 12 added
production hardening — HTTPS via Caddy, per-IP API rate limiting, security
headers, a secrets guard, and nightly `pg_dump` backups (see
[`docs/DEPLOY.md`](./docs/DEPLOY.md)).

A **post-v1 update phase** (Inbox & messaging overhaul + a Backup/Restore center) is
defined in **§15** of the spec — not yet started.

First run creates an admin from `BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD`
in `.env` — change these before production. Set `TELEGRAM_API_ID` / `TELEGRAM_API_HASH`
(from <https://my.telegram.org>) before logging in Telegram accounts.

## Credits

Developed by **Jahirul Islam** — <https://jahirulislam.info/>
