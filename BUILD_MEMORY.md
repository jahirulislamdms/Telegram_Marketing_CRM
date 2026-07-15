# BUILD_MEMORY.md — project state snapshot (handoff)

Self-contained memory so any AI/session can continue identically. Pairs with
[`CLAUDE.md`](./CLAUDE.md) (process) and the spec's §13/§14 (authoritative progress).
Last updated after **Phase 9**. Tests: **113 passing**. Commits `bb6d683` (P0+1) …
`2cf4503` (P9), all pushed to `origin/main`.

## Tech stack

FastAPI (Python 3.11) · Telethon (userbots) · aiogram v3 (bots, Phase 10) · Celery+Redis
(paced ticks / beat) · PostgreSQL (prod) / SQLite (local tests) · WebSockets (inbox) ·
React + Vite + TypeScript + zustand + react-router (no UI kit; hand-rolled CSS in
`index.css`) · Caddy · Docker Compose. bcrypt + JWT (python-jose) auth. openpyxl (Excel
import). python-socks (proxies).

## Repo layout (key)

```
backend/app/        config.py, main.py, realtime.py (WS), cli.py (ensure-admin)
  db/models/        user, event, account, proxy, contact, inbox, sender, destination, campaign, warmup, types(JSONType), constants(enums)
  db/migrations/    0001_users_and_events … 0008_campaigns  (env.py honors ALEMBIC_URL)
  auth/             security.py (bcrypt+JWT), dependencies.py (get_current_user, require_manager/admin)
  api/              auth, users, audit, accounts, proxies, warmup, contacts, inbox, sender, destinations, campaigns, health
  services/         users, auth, audit, accounts, proxies, contacts, inbox, inbox_consumer, engine_client, warmup, sender, destinations, campaigns
backend/engine/     app.py (private HTTP API :9100), manager.py (SessionManager, Telethon), actions.py, health.py, resolve.py, listener.py, proxy.py, schemas.py, main.py
backend/worker/     celery_app.py (beat: warmup/sender/campaigns tick), tasks/{warmup,sending,campaigns}.py, antiban/{spintax,pacing}.py
frontend/src/       api/client.ts, store/auth.ts, lib/{theme,useInboxSocket}, components/{AppLayout,ProtectedRoute,*Modal}, pages/{Login,Dashboard,Accounts,Warmup,Contacts,Pipeline,Inbox,GroupsChannels,Sender,Campaigns,Staff}
```

## What each phase delivered

- **P0 Foundation** — repo scaffold, docker-compose (dev+prod), Caddyfile, Alembic, base
  FastAPI `/health` + `/health/ready`. `DATABASE_URL` override added (12-factor; lets the
  app run on SQLite locally).
- **P1 Auth/RBAC** — `users`,`events` (0001). bcrypt+JWT (access/refresh), `require_roles`.
  `/api/auth/*`, admin `/api/users`, `/api/audit`. `app.cli ensure-admin`. React login,
  protected routes, zustand auth store, theme toggle (persisted per user).
- **P2 Accounts & login** — `accounts`,`proxies` (0002). Engine rebuilt as internal FastAPI
  (:9100) owning Telethon: QR/phone/session login, file sessions under `sessions/` for
  restart persistence, proxy→python-socks. `engine_client` (httpx). `/api/accounts` (CRUD,
  status, reconnect, login flows, logout), `/api/proxies` (parse/import/dedupe/auto-assign).
  Accounts page + login modal (qrcode.react).
- **P3 Health** — `engine/health.py` (`classify_spambot_reply` + spam/ban/unspam/unfreeze),
  `/api/accounts/{id}/health/*`, manual status override, **auto-quarantine** on limited/banned.
  `AUTO_QUARANTINE_ON_WARNING`. Accounts spam column + health modal.
- **P4 Warmup** — `warmup_runs/participants/partners` (0003). `engine/actions.py` join_chat +
  send_dm. `services/warmup.py` `run_tick` (staged ramp: advance on schedule, one paced action
  per participant — join un-joined group else chit-chat peer/partner). `/api/warmup/*` + Celery
  `warmup.tick`. Warmup page.
- **P5 Contacts & pipeline** — `contacts` (0004). CSV+Excel import (openpyxl) w/ dedupe +
  consent rejection + template download; engine `resolve.py` (username/phone) + `/message`;
  `/api/contacts/*` (CRUD, import, resolve, message w/ consent guardrail, bulk); agents see own.
  Contacts page + message modal, Pipeline Kanban.
- **P6 Live inbox** — `conversations`,`messages` (0005). `app/realtime.py` (WS ConnectionManager +
  best-effort Redis bridge, **in-process fallback**); `/ws/inbox` (token query param);
  `engine/listener.py` (NewMessage→Redis `inbox:incoming`) + `inbox_consumer.py`;
  `services/inbox.py` (record in/out, contact-link + stage advance, **opt-out auto-honor**,
  status sync); `/api/inbox/*` (list/thread/read/status/send/bulk/simulate-incoming); engine
  `send_file`. Inbox 3-pane page + `useInboxSocket`.
- **P7 Sender + anti-ban** — `send_jobs`,`send_targets` (0006). `worker/antiban/` spintax + pacing
  (rotate/cap/delay/window). `services/sender.py` `run_tick` (rotation, caps, suppress-link-first,
  contact new→contacted, flood→quarantine+pause) + `build_executor` (send + **lands in inbox**).
  Engine send returns `{sent,error}` on flood so all callers back off. `/api/sender/*` + Celery
  `sender.tick`. Sender page.
- **P8 Groups/Add members** — `destinations`,`group_memberships` (0007). engine `resolve_destination`
  + `add_member` (direct-add via InviteToChannel/AddChatUser + **invite-link fallback** via
  ExportChatInvite→DM). `services/destinations.py` (register, add_members [consented + typed
  find-or-create, **excludes already-members**], `run_add_tick`, `already_member_contact_ids`).
  Contacts `in_destination`/`not_in_destination` filters. `/api/destinations/*`. Groups page.
- **P9 Campaigns + A/B** — `templates`,`campaigns`,`campaign_targets` (0008). `services/campaigns.py`:
  segment builder (consent + source/stage/tag + **exclude_in_destination**), materialize (**A/B split**
  `contact_id % n`, **drip** scheduled_at offsets), `run_tick` (message→send+inbox / add→add_member+
  membership, flood→pause), `ab_report`. `/api/templates` + `/api/campaigns/*` + Celery
  `campaigns.tick`. Campaigns page (A/B templates, builder, A/B results table).

## Engine internal API (`:9100`, private) — routes so far

`GET /health`, `GET|POST /clients/{id}/status|start|logout`;
login: `/login/qr` (POST/GET), `/login/qr/password`, `/login/phone/send-code`,
`/login/phone/sign-in`, `/login/session`;
health: `/health/{spam-check,ban-check,unspam,unfreeze}`;
warmup: `/warmup/{join,send}`; messaging: `/message`, `/send-file`;
resolve: `/resolve/{username,phone}`; destinations: `/destination/{resolve,add}`.
All accept a `Credentials` body `{api_id, api_hash, proxy?}` (+ action fields). The
backend `engine_client` wraps each; on network/5xx it raises `EngineUnavailable`.

## Key decisions (why things are the way they are)

- Engine is DB-free where possible; the backend passes creds/data and persists results
  (except the inbox consumer, which writes incoming messages). Postgres concurrency is
  fine; the "single owner" rule is specifically about Telethon SQLite session files.
- Paced ops share the tick pattern + `worker/antiban/pacing.py`. `eligible_accounts` =
  `status='active'` and `session_ref` not null (warming/quarantined excluded).
- `DATABASE_URL` overrides POSTGRES_* (sqlite for local); `ALEMBIC_URL` overrides for
  migrations. `REDIS_HOST=127.0.0.1` makes local Redis probes fail fast → in-process WS.
- Tests monkeypatch `realtime.startup`/`inbox_consumer.startup` to no-ops (conftest) so
  the per-test lifespan doesn't hang probing the unreachable `redis` host.
- Typed identifiers (contacts import-by-typing, add-members) are find-or-created as
  contacts with `consent=true` (operator asserts ownership) — documented, defensible.

## Remaining phases (spec §9)

- **P10 Multi-bot console** — host **multiple aiogram bots** in the engine (add by BotFather
  token, polling/webhook, start/stop/remove); per-bot started/active dashboard; **two-way bot
  inbox** (users message the bot, staff reply — like the account inbox but for bot chats);
  send message to a user or a selected group/channel; **post to channels with image+text**;
  add bot to groups; **UTM opt-in deep-links** per source; subscriber capture; broadcast; AFK
  auto-reply. Tables (spec §5): `bots`, `bot_subscribers`, `bot_conversations`, `bot_messages`,
  `referrals`. **New dependency: `aiogram` v3** — add to `backend/pyproject.toml`; the engine
  will host aiogram bots alongside Telethon userbots (separate manager). Reuse the inbox WS
  pattern for the bot inbox. *Done when:* two bots run from pasted tokens, an incoming bot
  message appears in the bot inbox and staff can reply, and a text+image post reaches a channel.
- **P11 Dashboard, analytics + referral** — system-monitoring Dashboard (live account health,
  throughput, queue depth, quarantines, proxy-pool health, running campaigns via WebSocket),
  event tracking, marketing analytics (funnel, per-source conversion, per-account, campaign/A-B),
  UTM attribution, referral links/rewards.
- **P12 Hardening & deploy** — HTTPS via Caddy, `pg_dump` backups, rate-limited API, secrets,
  prod compose, Ubuntu + Windows install docs.

## How to resume in one line

Read spec §13/§14 for status → pick the next unchecked phase → follow the CLAUDE.md
recipe → verify (tests + migration + frontend build + stub-engine browser E2E) →
tick §13, append §14 → commit + push.
