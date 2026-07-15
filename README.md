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

Production:

```bash
# set CADDY_SITE_ADDRESS=your-domain.com in .env first
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

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
Current status: **Phase 7 — Sender engine + anti-ban** complete (paced outreach with
account rotation, per-account caps, randomized delays, active-hour windows, spintax,
flood auto-pause; campaign sends land in the inbox). Phases 0–6 done (foundation,
auth/RBAC, accounts & login, account health, warmup, contacts & pipeline, live inbox).

First run creates an admin from `BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD`
in `.env` — change these before production. Set `TELEGRAM_API_ID` / `TELEGRAM_API_HASH`
(from <https://my.telegram.org>) before logging in Telegram accounts.

## Credits

Developed by **Jahirul Islam** — <https://jahirulislam.info/>
