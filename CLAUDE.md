# CLAUDE.md — working instructions for this project

> Read this first. It defines the GOAL, the per-phase PROCESS, and the environment
> quirks so any AI/session can continue the build identically. Detailed state and
> recipes are in [`BUILD_MEMORY.md`](./BUILD_MEMORY.md). The master spec is
> [`Telegram_Marketing_CRM_Structure.md`](./Telegram_Marketing_CRM_Structure.md).

## The goal

Build the **Telegram Marketing CRM** described in the spec, **one phase at a time**
(13 phases, 0–12). Each phase is self-contained with its own acceptance test
("Done when…" in spec §9). Build and verify in order. Internal company use only —
target **consented contacts** and **company-owned** groups/channels.

## THE ONE RULE YOU MUST NEVER SKIP

After finishing each phase (and any notable change):

1. Tick the item in **§13 Build Progress Tracker** (`[ ]`→`[x]`) in the spec file.
2. Append a dated entry to **§14 Activity Log** (newest at the bottom) in the spec file.
3. Then **commit and push** (see Git below).

This is the source of truth for progress. Do it as part of the same task, every time.

## Current status

Phases **0–11 are DONE**. **Phase 12 (Hardening & deploy) is next.**
Always confirm current status from spec **§13/§14** — they are authoritative.
`BUILD_MEMORY.md` has the condensed per-phase record and the remaining-phase plan.

## Environment (this machine)

- Windows 11, **PowerShell** primary; a **Git Bash** tool is also available (POSIX).
- **Python 3.11** and **Node 22** are installed. **NO Docker, NO Redis, NO Postgres**
  running locally. The spec's acceptance tests assume `docker compose up`, but the
  stack cannot be launched here — verify by running services directly (see below).
- Scratchpad dir for temp files (session-specific): use it, never `/tmp`.

## Architecture invariants (do not violate)

- The **Telegram Engine Service** (`backend/engine/`) is the **ONLY** process that
  owns Telethon clients (and, from Phase 10, aiogram bots). The API and Celery
  workers **never** open a Telethon client directly — they call the engine's private
  HTTP API via `app/services/engine_client.py`. This prevents session/DB-lock
  collisions. Add new Telegram actions as: engine action → `SessionManager` method →
  engine route (`engine/app.py`) → `engine_client` function → backend service/API.
- **Consent guardrail:** every outreach targets a contact with `consent=true` and
  `opted_out=false`. Opt-out replies are auto-honored (inbox detects "stop").
- **RBAC:** roles admin/manager/agent. Most management is Admin/Manager
  (`require_manager`); agents see/act on their **own assigned** contacts/inbox only.
- **Anti-ban pacing** lives in `backend/worker/antiban/` (spintax, rotation, caps,
  delays, windows) and is reused by warmup/sender/campaigns/add-members ticks.
- **Paced operations use a "tick" model:** an idempotent `run_tick(db, obj, now,
  execute)` that does one action per eligible account, rotated, respecting
  cap/delay/window, and on a flood/peer-flood warning **quarantines the account and
  pauses**. A Celery beat task calls the tick every N seconds; an API `…/tick`
  endpoint calls the same for manual/testing runs.

## Per-phase build recipe

1. **Models** (`backend/app/db/models/*.py`) + register in `models/__init__.py`.
   String enums stored as `String` columns with named `CheckConstraint`s; JSON via
   `app/db/models/types.py` `JSONType` (JSONB on PG, JSON on SQLite).
2. **Migration** (`backend/app/db/migrations/versions/000N_*.py`) — hand-written,
   revision id `000N_<slug>`, `down_revision` = previous, named constraints matching
   the models. Verify up+down on SQLite (see recipe).
3. **Engine** (if Telegram side effects): action in `engine/actions.py` (or a new
   module), `SessionManager` method, route in `engine/app.py`, schema in
   `engine/schemas.py`, then `engine_client` function.
4. **Service** (`backend/app/services/*.py`) — pure/testable logic + orchestration.
5. **Schemas** (`backend/app/schemas/*.py`) + **API router** (`backend/app/api/*.py`),
   registered in `backend/app/main.py`.
6. **Celery task** (`backend/worker/tasks/*.py`) + beat schedule if it's paced.
7. **Frontend**: `frontend/src/api/client.ts` additions, a page in
   `frontend/src/pages/`, nav in `components/AppLayout.tsx`, route in `App.tsx`, CSS
   in `src/index.css`. Build with `npm run build` (must pass `tsc --noEmit`).
8. **Tests** (`backend/tests/test_*.py`) — pure-logic units + API integration with
   the **engine mocked** (`monkeypatch.setattr(engine_client, "…", fake)`).
9. **Verify**: backend tests green, migration up/down, frontend build, and a **browser
   E2E** driving the real flow with a stub engine (see recipe).
10. **§13/§14 + commit + push.**

## Verification recipes

Deps for running backend/tests (no Docker): the app needs fastapi/uvicorn/
sqlalchemy/aiosqlite/bcrypt/python-jose/email-validator/psycopg/pytest/pytest-asyncio/
telethon/python-socks/redis/openpyxl. Cleanest: `cd backend && python -m venv .venv &&
.venv/Scripts/pip install -e ".[dev]"` (pyproject lists them). (In prior sessions
these were installed to a scratch `pydeps` dir and put on `PYTHONPATH` alongside
`backend` — either works.)

- **Backend tests** (SQLite via `conftest.py` `get_db` override; `realtime`/
  `inbox_consumer` startup is monkeypatched off in conftest so Redis isn't probed):
  `PYTHONPATH="<deps>;backend" SESSIONS_DIR=<scratch> python -m pytest backend/tests -q`
- **Migration up/down on SQLite** (env.py honors `ALEMBIC_URL`):
  `ALEMBIC_URL="sqlite:///x.db" python -m alembic upgrade head` then `downgrade base`.
- **Local end-to-end** (no Telegram, no Redis, no Postgres):
  1. Seed a SQLite DB: run a small script with `DATABASE_URL=sqlite+aiosqlite:///e2e.db`
     that does `Base.metadata.create_all` + creates an admin + any seed rows.
  2. Start a **stub engine** — a tiny FastAPI in the scratchpad implementing just the
     `/clients/{id}/…` routes the phase uses, returning canned JSON — on `:9100`.
  3. Start backend: `DATABASE_URL=sqlite+aiosqlite:///e2e.db ENGINE_URL=http://127.0.0.1:9100
     REDIS_HOST=127.0.0.1 python -m uvicorn app.main:app --port 8000` (REDIS_HOST=127.0.0.1
     makes the realtime Redis probe fail fast → in-process WS broadcast).
  4. Start Vite: `cd frontend && npm run dev -- --port 5173`.
  5. Drive the browser (login admin@example.com / admin12345). **Screenshots may time
     out this environment** — use `read_page` / `get_page_text` / element `ref`s +
     `form_input` instead. Always tear down servers and clean scratch after.

## Conventions & gotchas

- **Cross-test pollution:** the SQLite test DB is shared across all test files;
  anything selecting globally (e.g. sender/campaign `eligible_accounts`) sees other
  tests' rows. Isolate in such tests: `UPDATE accounts SET session_ref=NULL,
  status='logged_out'` (service tests) or PATCH other accounts to `logged_out` via API.
- **Structured send returns:** engine `send_dm`/`send_file`/`add_member` return
  `{sent/state, error}` on flood/peer-flood (not raised) so callers back off; always
  check the result, not just for exceptions.
- **Bootstrap admin** in Docker: backend command runs `alembic upgrade head &&
  python -m app.cli ensure-admin && uvicorn …`. Local E2E seeds the admin directly.
- **Not live-tested** anywhere: real Telegram login/send/add and real FloodWait — they
  need live API creds + accounts + network. Code paths are complete; the HTTP
  contracts are verified with stub engines. Say so honestly in §14.

## Git

- Repo: branch `main`, remote `origin` =
  https://github.com/jahirulislamdms/Telegram_Marketing_CRM — **push works** (a Windows
  git credential helper is configured; `gh` CLI is not installed).
- Commit per phase; never commit `.env`, `node_modules`, `dist`, `sessions/*`, or DB
  files (all gitignored). `.gitattributes` normalizes to LF.
- End commit messages with:
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
