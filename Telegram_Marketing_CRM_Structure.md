# Telegram Marketing CRM — Project Structure & Build Plan

**Version:** 1.0
**Purpose:** Master specification for building a self-hosted, multi-user Telegram marketing CRM. Written to be handed to Claude Code phase-by-phase for token-efficient implementation.
**Use type:** Internal company use only. Marketing to **consented contacts** and management of **company-owned** channels/groups.

---

## 1. Scope

The tool operates on the company's **own consented contacts** and **company-owned** channels/groups. Features to build:

- **Master login for Telegram accounts** — QR code, phone number, or manual API, using ONE shared API ID/HASH across all accounts. Sessions saved to disk = one-time login.
- **Unlimited Telegram accounts**, each optionally bound to a proxy pulled automatically from the proxy pool (or run with no proxy).
- **Account health** — spam-check (via @SpamBot), ban-check, auto-unspam/unfreeze requests, warmup, live status monitoring, auto-quarantine.
- **Profile management** — edit first/last name, username, bio, photo per account (manual or automated).
- **Contact / lead manager** — CSV import supporting **both phone-number leads and username leads** (we have both kinds), dedupe, tag by source (online/offline store), phone→Telegram-user resolution, username→Telegram-user resolution, consent + opt-out tracking.
- **CRM pipeline** — each contact moves through stages: New → Contacted → Replied → Joined → Customer → Opted-out.
- **Live conversation inbox** — staff chat with contacts in real time, from any logged-in account, in a web UI.
- **Sender engine** — text + image + optional link, template spinning, multi-day drip sequences, account rotation, pacing, per-account caps.
- **Invite + add** — deliver personal invite links; attempt direct-add to group/channel with automatic invite-link fallback (own consented contacts only).
- **Bot layer** — opt-in ("Start") funnel with UTM deep-links, broadcast to opted-in subscribers, lead capture, AFK auto-reply.
- **Campaigns** — segmented, scheduled, with A/B template testing.
- **Referral program** — personal invite links + reward tracking for subscribers who bring others.
- **Dashboard & analytics** — system-monitoring dashboard (accounts health, live sending throughput, queue depth, quarantines, campaign status, errors) plus marketing analytics (delivered / replied / joined / opted-out, per-source conversion, per-account health, per-campaign & A/B performance, UTM attribution).
- **Fully customizable Settings** — every tunable (all anti-ban delays/limits/warmup, proxy pool, API ID/HASH, message windows) editable from the Settings UI without touching code.
- **Multi-user access** — email/password login, roles (Admin / Manager / Agent), audit log.
- **Deployment** — Docker Compose, runs on Ubuntu VPS or Windows, reachable over the internet via HTTPS.

**Consent guardrail (functional requirement):** every outreach action targets a contact that exists in the contacts table with `consent = true` and `opted_out = false`. Opt-out replies are honored automatically and permanently.

---

## 2. Technology Stack

| Layer | Choice | Notes |
|---|---|---|
| Backend API | **Python 3.11+ / FastAPI** | Same language as Telegram engine → one codebase |
| Telegram (userbot) | **Telethon** | Multi-account, session files, MTProto |
| Telegram (bot) | **aiogram v3** | Opt-in funnel, broadcast |
| Async worker / scheduler | **Celery + Redis** | Pacing, rotation, drip, warmup timing |
| Database | **PostgreSQL 15+** | All persistent data |
| Cache / broker / realtime pub-sub | **Redis** | Celery broker + WebSocket fan-out |
| Realtime inbox | **WebSockets (FastAPI)** | Live conversation updates |
| Frontend | **React + Vite + TypeScript** | Web UI |
| UI components | **shadcn/ui + Tailwind** | Inbox, pipeline, forms |
| Auth | **JWT (access + refresh)** | Email/password, RBAC |
| Reverse proxy / TLS | **Caddy** (or Nginx) | Auto HTTPS |
| Packaging | **Docker + Docker Compose** | Same install on Ubuntu VPS or Windows |

---

## 3. Architecture

```
                         ┌──────────────────────────────┐
   Browser (staff) ──────►  React Web UI (Vite)          │
   from anywhere         └───────────────┬───────────────┘
                                         │ HTTPS + WSS
                          ┌──────────────▼───────────────┐
                          │  Caddy (reverse proxy + TLS)  │
                          └──────────────┬───────────────┘
                                         │
                          ┌──────────────▼───────────────┐
                          │  FastAPI  (REST + WebSocket)  │  ← auth, RBAC, CRUD, inbox API
                          └───┬───────────────┬───────────┘
                              │               │
                 ┌────────────▼───┐     ┌─────▼──────────────┐
                 │  PostgreSQL     │     │  Redis (broker +   │
                 │  (all data)     │     │  pub/sub + cache)  │
                 └────────────▲───┘     └─────▲──────────────┘
                              │               │
                 ┌────────────┴───────────────┴────────────┐
                 │   Celery Workers + Beat (scheduler)      │
                 │   - sender engine / pacing / rotation    │
                 │   - warmup, drip, campaigns              │
                 └────────────────────┬─────────────────────┘
                                      │
                 ┌────────────────────▼─────────────────────┐
                 │   Telegram Engine Service (dedicated)     │
                 │   - Telethon session manager (userbots)  │
                 │   - aiogram bot                          │
                 │   - proxy per account                    │
                 │   - incoming message listener → inbox    │
                 └──────────────────────────────────────────┘
```

**Key design rule:** Telegram sessions are owned **only** by the Telegram Engine Service (one process/container). The API and workers never open a Telethon client directly — they enqueue jobs, and the engine executes them. This prevents session/database-lock collisions across many accounts.

---

## 4. Repository Layout

```
telegram-crm/
├── docker-compose.yml
├── docker-compose.prod.yml
├── .env.example
├── Caddyfile
├── README.md
│
├── backend/
│   ├── pyproject.toml
│   ├── app/
│   │   ├── main.py                # FastAPI entrypoint
│   │   ├── config.py              # settings from env
│   │   ├── db/                    # SQLAlchemy models, session, migrations (Alembic)
│   │   │   ├── models/
│   │   │   └── migrations/
│   │   ├── auth/                  # JWT, password hashing, RBAC dependencies
│   │   ├── api/                   # routers
│   │   │   ├── accounts.py
│   │   │   ├── warmup.py          # warmup runs + external partners
│   │   │   ├── contacts.py        # import (csv/excel), bulk actions
│   │   │   ├── inbox.py           # unified inbox + websocket
│   │   │   ├── destinations.py    # groups/channels + add-members
│   │   │   ├── campaigns.py
│   │   │   ├── bot.py             # bot console: send/post/manage
│   │   │   ├── analytics.py       # + dashboard metrics
│   │   │   ├── users.py           # staff, roles
│   │   │   └── settings.py        # config + proxy pool + templates
│   │   ├── schemas/               # Pydantic
│   │   └── services/              # business logic
│   │
│   ├── engine/                    # Telegram Engine Service (separate container)
│   │   ├── manager.py             # session registry, login (qr/phone/api)
│   │   ├── health.py              # spambot / ban / unfreeze checks
│   │   ├── sender.py              # send text/media/link, invite, add+fallback
│   │   ├── listener.py            # incoming messages → inbox → websocket
│   │   ├── profile.py             # edit name/username/bio/photo
│   │   ├── bots_manager.py        # hosts multiple aiogram bots (add/start/stop)
│   │   └── proxy.py               # per-account proxy binding
│   │
│   ├── worker/                    # Celery
│   │   ├── celery_app.py
│   │   ├── tasks/
│   │   │   ├── sending.py         # rotation, pacing, caps
│   │   │   ├── warmup.py
│   │   │   ├── drip.py
│   │   │   ├── campaigns.py
│   │   │   └── health.py
│   │   └── antiban/               # rotation, delays, limits, flood handling
│   │
│   └── tests/
│
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   └── src/
│       ├── api/                   # typed API client
│       ├── pages/
│       │   ├── Login.tsx
│       │   ├── Dashboard.tsx
│       │   ├── Accounts.tsx
│       │   ├── Warmup.tsx
│       │   ├── Contacts.tsx
│       │   ├── Pipeline.tsx
│       │   ├── Inbox.tsx
│       │   ├── GroupsChannels.tsx   # "Add members"
│       │   ├── Campaigns.tsx
│       │   ├── Bot.tsx              # full bot console
│       │   ├── Analytics.tsx
│       │   ├── Staff.tsx
│       │   ├── Settings.tsx
│       │   └── About.tsx
│       ├── components/
│       └── store/                 # auth + websocket state
│
└── sessions/                      # Telethon session files (persisted volume, gitignored)
```

---

## 5. Database Schema (core tables)

**users** (staff) — id, email (unique), password_hash, full_name, role (admin/manager/agent), theme (dark/light), is_active, created_at, last_login.

**accounts** (Telegram accounts) — id, label, phone, api_id, api_hash, session_ref, proxy_id (nullable, auto-assigned from pool), status (active/warming/quarantined/banned/logged_out), warmup_stage, warmup_started_at, daily_cap, actions_today, last_action_at, spam_state, created_at.

**proxies** (proxy pool) — id, raw (original pasted string), type (socks5/http/mtproto), host, port, username, password, is_active, assigned_account_id (nullable), last_checked_at, health (ok/dead/unknown), notes. Proxies are pasted in bulk in Settings; the engine auto-assigns a free, healthy proxy from the pool to each account (one proxy per account).

**contacts** (leads) — id, name (nullable — falls back to username, then phone, as the display label), lead_type (phone/username), phone (nullable), username (nullable), telegram_user_id (nullable, filled by resolution), resolution_status (pending/resolved/no_telegram/failed), source (online/offline/campaign tag), stage (new/contacted/replied/joined/customer/opted_out), consent (bool), opted_out (bool), assigned_account_id (nullable), assigned_agent_id (nullable), utm (json), tags (json), created_at, last_contacted_at.

**conversations** — id, contact_id, account_id, last_message_at, unread_count, status.

**messages** — id, conversation_id, direction (in/out), account_id, sender (contact/agent id), type (text/image/voice/link), body, media_ref (nullable — image/voice file), tg_message_id, status (queued/sent/delivered/failed/read), created_at.

**templates** — id, name, body (with spintax), media_ref (nullable), include_link (bool), link_url (nullable), variant_group (for A/B), created_at.

**campaigns** — id, name, segment (json filter), template_group_id, schedule (json), status (draft/running/paused/done), ab_test (bool), created_by, created_at.

**campaign_targets** — id, campaign_id, contact_id, template_variant_id, account_id, scheduled_at, sent_at, result (sent/replied/joined/failed/skipped).

**destinations** (target groups/channels) — id, title, tg_entity_id, type (group/channel), invite_link (nullable), added_via (account_id used), created_at.

**group_memberships** (already-in-destination tracking) — id, contact_id, destination_id, state (added/invited/joined/failed), method (direct_add/invite), account_id, created_at. Powers the "already-in-destination" tag and exclusion filter.

**bots** (multiple, self-hosted) — id, name, token, mode (polling/webhook), status (running/stopped/error), webhook_url (nullable), started_count, active_count, created_at. Each bot runs as its own aiogram instance inside the engine service; add by pasting a BotFather token.

**bot_subscribers** — id, bot_id, telegram_user_id, contact_id (nullable link), utm_source, started_at, last_active_at, is_active, is_subscribed.

**bot_conversations** — id, bot_id, subscriber_id, last_message_at, unread_count, assigned_agent_id (nullable), status.

**bot_messages** — id, bot_conversation_id, direction (in/out), sender (subscriber/agent id), type (text/image/voice/link), body, media_ref (nullable), tg_message_id, created_at.

**referrals** — id, referrer_subscriber_id, invite_code, invited_count, rewarded.

**events** (analytics/audit) — id, type, actor (user/account/system), entity_ref, meta (json), created_at.

**settings** (config + proxy pool + templates) — see §7.

### 5.1 Example import file (CSV / Excel)

Downloadable template shown in the Contacts import wizard. Phone leads and username leads can be mixed; leave the other identifier blank.

```csv
name,phone,username,source,consent
Ahmed Khan,+923001234567,,offline_store,true
Sara Ali,,@sara_ali,online_store,true
,+14155550123,,online_store,true
,,@no_name_user,online_store,true
```

- `name` — optional; if blank, the contact shows as its username, or its number if no username.
- `phone` — international format (with country code) for phone leads.
- `username` — Telegram @username for username leads.
- `source` — free tag (e.g. online_store / offline_store / campaign name).
- `consent` — must be `true`; rows without consent are rejected on import.

---

## 6. Anti-ban System (spec)

Implemented in `worker/antiban/` and enforced by the sender/warmup tasks. All values live in **settings** and are editable from the UI (§7).

- **Account rotation** — round-robin: never two consecutive actions from the same account. Configurable "rest rotation" (work N days → idle M days).
- **Warmup** — staged ramp for new accounts (e.g. stage 1: 1–2 actions/day, increasing over ~10–14 days to full cap). Warmup accounts perform "human" setup (join 1–2 channels, set photo/bio) before any marketing. Every stage duration and volume is configurable.
- **Per-account limits** — randomized daily + hourly caps (not identical each day). Tightest cap on new-contact imports (phone→user) — the riskiest action.
- **Delays** — randomized min/max delay between actions (default 40–180s). Simulated "typing…" + online status before send.
- **Time windows** — active hours / quiet hours per account; nothing sends overnight.
- **Message evasion** — spintax + emoji/word variation so no two messages are identical. Links suppressed in first-contact message (link only in later steps), configurable.
- **Network isolation** — proxies live in a central pool (pasted in Settings); the engine auto-assigns one free, health-checked proxy per account. No-proxy is allowed per account (with a UI warning when multiple no-proxy accounts share an IP). Stable device fingerprint per account across logins.
- **Flood/self-defense** — obey FloodWait with backoff; on PeerFlood / SpamBot warning / failed ban-check → auto-quarantine the account and pull it from rotation.
- **Consent guardrail** — only contacts with consent=true and opted_out=false are eligible; auto-honor "stop"/opt-out replies.

---

## 7. Config (anti-ban settings, UI-editable)

```yaml
rotation:
  one_action_per_account_switch: true
  rest_days_work: 4
  rest_days_idle: 2
warmup:
  enabled: true
  stages:                 # actions/day per stage
    - {days: 3, max_actions: 2}
    - {days: 4, max_actions: 5}
    - {days: 5, max_actions: 12}
  full_daily_cap: 30
limits:
  daily_cap_min: 20
  daily_cap_max: 40
  hourly_cap: 6
  contact_import_daily_max: 10
delays:
  between_actions_sec: {min: 40, max: 180}
  simulate_typing: true
windows:
  active_hours: {start: "09:00", end: "21:00"}
  timezone: "account_local"
messages:
  spintax: true
  suppress_link_first_message: true
proxy:
  require_proxy: false          # allow no-proxy per account
  warn_shared_ip: true
  auto_assign_from_pool: true    # engine pulls a free healthy proxy per account
  auto_health_check: true        # periodically test pooled proxies
safety:
  auto_quarantine_on_warning: true
  respect_floodwait: true
```

Every field above is editable from the **Settings** screen — nothing requires code changes. The **proxy pool** is managed here too: paste all proxies in bulk (one per line, formats like `host:port`, `host:port:user:pass`, or `socks5://user:pass@host:port`); the engine parses, health-checks, and auto-assigns a free proxy to each account.

---

## 8. Web UI Screens

### Design language

Modern, minimalist, card-based dashboard aesthetic (references provided):

- **Layout:** slim **icon sidebar** on the left for navigation; main area built from soft, **rounded cards** with generous spacing and subtle shadows; a top bar with date/search/profile.
- **Theme:** full **dark mode and light mode**, identical layout in both — only colors change. A **theme toggle button sits on the main Dashboard top bar** (also in Settings), applied across the *entire* system and persisted per user. A single accent color drives highlights, active nav, and charts; gradient fills on charts/metric cards.
- **Responsive / mobile-friendly:** the whole app adapts to phones and tablets — the icon sidebar collapses to a bottom/hamburger nav, cards stack in a single column, and the three-pane chat collapses to one pane at a time (list → chat → profile) on small screens.
- **Conversation layout (Inbox & Bot inbox):** **three panes** — conversation list (left) with avatars, name/ID, last-message preview and time + unread dot; the chat thread (center) with date separators, incoming/outgoing bubbles, timestamps; and a **contact/subscriber profile panel** (right) showing details, status/stage, tags, and recent history.
- **Composer:** text, image/file attach, emoji, **and a voice-message button** — record and send voice notes; received voice notes play inline with a waveform + duration.
- **Stack:** React + Tailwind + shadcn/ui, with a theme provider for dark/light tokens.

**1. Login** — email/password.

**2. Dashboard** — system-monitoring home: total/active/warming/quarantined accounts, live sending throughput, queue depth, today's sends vs caps, recent quarantines & errors, proxy-pool health, running campaigns at a glance. Real-time via WebSocket.

**3. Accounts** — registry of all accounts. Status badge per account (active / warmed up / not yet warmed up / in quarantine). Add account (QR / phone / API modal), remove, log in / re-login, view health (spam-check / ban-check / unspam / unfreeze), proxy auto-assigned from pool (or set none), and **manually override an account's status**.

**4. Warmup** — set up and launch warmup runs. Manually select which fleet accounts to warm; add **external personal partner accounts** by number or username (not logged in — the fleet messages them, you reply manually); add group/channel links for accounts to join; pick/edit the casual chit-chat templates; then **Start Warmup**. Shows per-account stage progress ("stage 2/3"), pause/stop. (Warmup accounts also chat with each other automatically.)

**5. Contacts** — the lead database.
  - Save contacts **with or without a name** — if no name is given, the list shows the username, or the number if there's no username. A username can be saved for any contact.
  - Import by **CSV or Excel**, with a downloadable **example file** (see §5.1); dedupe on import.
  - Tag by source (online/offline/campaign); consent/opt-out flags; resolution status (phone→user / username→user).
  - **Already-in-destination tag** — if a contact is already a member of a target group/channel, it's flagged, so you can filter and **exclude** them from adding or from marketing.
  - **Directly start a conversation** from a contact and **choose which account** sends it.
  - **Bulk select** to send a marketing message or add to a group/channel.

**6. Pipeline** — Kanban of contact stages (New → Contacted → Lead → Follow-up → Customer → Joined → Refused → Opted-out). Drag between stages, assign to agent, open a card to jump into its conversation.

**7. Inbox** — **unified, multi-account** conversation workspace. Every conversation any logged-in account receives appears here in one stream.
  - **Filters:** read / unread, by account, by status/stage, by tag, by assigned agent, by source.
  - **Set status per conversation** (syncs with Pipeline): New, Contacted, **Lead/Interested**, Follow-up, Customer, Joined, **Refused/Not-interested**, Opted-out, Blocked/Spam.
  - **Bulk selection + bulk actions:** mark status, assign to agent, add to campaign, add to group/channel, archive, export.
  - Three-pane layout (conversation list · chat · contact profile panel).
  - Send text / image / link / **voice message**; every thread shows which account is talking.
  - **Campaign messages appear here** — Inbox and Campaigns share one message history, so campaign sends and manual replies live in the same thread.

**8. Groups & Channels ("Add members")** — manage destinations and run add jobs.
  - Register/select **destination group(s) and channel(s)**.
  - Build the member list two ways in the same input area: **pick from the contact list** (it appears here for selection) **or type numbers/usernames directly** into the same box.
  - Run **Add members** — attempts **direct-add** and **auto-falls back to invite link**; spread across accounts, paced by anti-ban limits.
  - Results view (added / invited / joined / failed); feeds the "already-in-destination" tag back to Contacts.

**9. Campaigns** — segment builder (filter by source/stage/tag, exclude already-in-group), template editor (spintax + A/B variants), schedule + multi-day drip, choose action (message / invite / add), live progress and A/B results, pause/resume.

**10. Bots (multi-bot management console)** — add and run **multiple bots**, all hosted on this same server, managed from one place.
  - **Add a bot in seconds:** paste its BotFather token → the server starts hosting it (polling or webhook) automatically. Start / stop / remove each bot. No separate hosting or setup needed.
  - **Per-bot dashboard:** how many people started it, how many are active/subscribed.
  - **Two-way conversations:** users message the bot, and staff reply to those users right here (a bot inbox, like the account Inbox but for bot chats — same three-pane layout, text/image/link/**voice**). Full back-and-forth conversation per user.
  - **Send marketing messages** from here — to a specific user, or to a specific group/channel you select.
  - **Post to your channels/groups** with **image + text**; edit/manage posts.
  - Add a bot to groups/channels; manage subscribers; opt-in deep-links per source (UTM); AFK/auto-reply.
  - Designed to be **simple to use** — pick a bot from the list and do everything for it in one interface.

**11. Analytics** — funnel (contacted→replied→joined→customer), per-source conversion, per-account health, campaign + A/B results, referral leaderboard.

**12. Staff** — manage users, roles, activity/audit log (Admin only).

**13. Settings** — fully customizable, no code: all anti-ban config (§7 — delays, limits, warmup stages, windows, rotation), warmup chit-chat templates, **proxy pool** (bulk paste + health status), API ID/HASH, message defaults, theme.

**14. About** — overview of the CRM and its full feature list, version, and credits: **Developed by Jahirul Islam** — [https://jahirulislam.info/](https://jahirulislam.info/).

## 8.1 Roles / permissions

- **Admin** — everything, incl. staff management, accounts, settings.
- **Manager** — dashboard, accounts, warmup, contacts, pipeline, inbox, groups & channels, campaigns, bot, analytics; no staff/settings.
- **Agent** — assigned inbox conversations + own contacts only.

---

## 9. Phased Build Plan (each phase = one Claude Code task)

Each phase is self-contained with its own acceptance test. Build and verify in order.

**Phase 0 — Foundation.** Repo scaffold, Docker Compose (postgres, redis, backend, worker, engine, frontend, caddy), `.env`, Alembic, base FastAPI app, health endpoint. *Done when:* `docker compose up` runs all services and `/health` returns 200.

**Phase 1 — Auth & staff/RBAC.** users table, email/password, JWT, roles, audit log, React login + protected routes. *Done when:* admin can log in, create staff, roles enforced.

**Phase 2 — Account manager & login.** Telegram Engine Service; shared API ID/HASH; QR / phone / API login; session persistence; proxy binding; accounts UI. *Done when:* an account logs in via QR and survives a restart without re-login.

**Phase 3 — Account health & manual status.** spam-check (@SpamBot), ban-check, unspam/unfreeze, status badges, manual status override, auto-quarantine hook. *Done when:* health status shows correctly, a flagged account auto-quarantines, and status can be manually overridden.

**Phase 4 — Warmup.** Warmup screen; select fleet accounts; add external partner accounts (number/username, no login); add group/channel links to join; chit-chat templates; staged ramp; fleet-to-fleet + fleet-to-partner messaging; stagger many accounts. *Done when:* selected accounts join the given groups and exchange staged messages, advancing through warmup stages on the configured schedule.

**Phase 5 — Contacts & CRM pipeline.** contacts schema (phone + username lead types, saved by name), CSV **and Excel** import + example file + dedupe, tagging, consent/opt-out, phone→user and username→user resolution, direct-message-with-account-choice, bulk actions, Kanban pipeline. *Done when:* CSV/Excel imports both lead types, dedupes, resolves users, stages update, and a contact can be messaged from a chosen account.

**Phase 6 — Unified live inbox.** conversations/messages, engine listener → Redis pub/sub → WebSocket, multi-account single stream, filters (read/unread/account/status/tag), per-conversation status, bulk selection + bulk actions, send text/image/link. *Done when:* an incoming message from any account appears live in one inbox, status/bulk actions work, and an agent can reply.

**Phase 7 — Sender engine + anti-ban.** Celery sending tasks, rotation, caps, delays, windows, spintax, flood handling, quarantine. Campaign/manual sends appear in the inbox thread. *Done when:* a test send to consented contacts rotates accounts, respects caps/delays, lands in the inbox, and auto-pauses on a warning.

**Phase 8 — Groups & Channels ("Add members").** register destinations; build member list from contacts or direct number/username entry; direct-add + invite fallback; group_memberships tracking + "already-in-destination" tag/exclusion. *Done when:* selected/typed members are added-or-invited, results recorded, and already-members are tagged and excludable.

**Phase 9 — Campaigns + drip + A/B.** segment builder (with exclude-already-in-group), template variants, scheduling, drip steps, action type (message/invite/add), A/B measurement. *Done when:* a scheduled multi-step campaign runs across segments and reports A/B results.

**Phase 10 — Multi-bot console.** host multiple aiogram bots in the engine, add-by-token (polling/webhook) with start/stop/remove; per-bot started/active dashboard; **two-way bot inbox** (users message the bot, staff reply); send message to user or selected group/channel; post to channels with image+text; add bot to groups; UTM opt-in deep-links; subscriber capture; broadcast; AFK. *Done when:* two bots run from pasted tokens, an incoming bot message appears in the bot inbox and staff can reply, and a text+image post reaches a selected channel.

**Phase 11 — Dashboard, analytics + referral.** system-monitoring Dashboard (live account health, throughput, queue depth, quarantines, proxy-pool health, running campaigns via WebSocket), event tracking, marketing analytics, UTM attribution, referral links/rewards. *Done when:* the Dashboard shows live system state and analytics show funnel + per-source conversion and referral counts.

**Phase 12 — Hardening & deploy.** HTTPS via Caddy, backups (pg_dump), rate-limited API, secrets, prod compose, Ubuntu + Windows install docs. *Done when:* reachable over the internet via HTTPS on a VPS with automated backups.

**Future phase (not v1):** Telegram Mini App + Stars payments (separate large project).

---

## 10. Deployment

- **Single command:** `docker compose -f docker-compose.prod.yml up -d`.
- **Ubuntu VPS:** install Docker + Compose; point a domain at the server; Caddy issues HTTPS automatically.
- **Windows:** Docker Desktop; same compose file.
- **Access from anywhere:** via the domain over HTTPS; JWT auth + RBAC protect it. Recommend restricting by strong passwords and (optionally) IP allowlist / 2FA in a later iteration.
- **Persistence:** named volumes for `postgres`, `redis`, and `sessions/` (Telethon sessions). Nightly `pg_dump` backup.

---

## 11. Legal & Compliance Notes

- Only contact people who gave consent (form opt-in). Store proof of consent and source per contact.
- Always honor opt-out immediately and permanently.
- Include who-you-are + an opt-out path in outreach.
- Comply with local marketing/privacy law for phone-based outreach (e.g. GDPR/PECR-style consent, local equivalents) — this tool tracks consent but you are responsible for lawful use.
- Multi-account userbot automation is tolerated but not endorsed by Telegram; the anti-ban system reduces risk but cannot eliminate it. Keep the safe Bot API funnel as the primary long-term channel.

---

## 12. About the CRM

A self-hosted, multi-user Telegram marketing CRM for reaching consented contacts and growing owned channels/groups, with a modern card-based dashboard, dark/light themes, and a fully mobile-friendly UI.

**Full feature list**

- Multi-user staff login (email/password) with roles (Admin / Manager / Agent) and audit log.
- Master Telegram login — QR / phone / API, one shared API ID/HASH, one-time saved sessions, unlimited accounts.
- Account manager with health tools (spam-check, ban-check, unspam, unfreeze) and manual status control.
- Warmup module — staged ramp, external personal partners, group joins, chit-chat templates.
- Contact/lead manager — CSV & Excel import, phone + username leads, name optional, dedupe, tags, consent/opt-out, already-in-group tagging.
- CRM pipeline (Kanban) and unified multi-account Inbox with filters, statuses, bulk actions, and voice messages.
- Groups & Channels "Add members" — direct-add with invite-link fallback.
- Campaigns — segments, spintax templates, A/B testing, drip sequences, scheduling.
- Multi-bot console — host multiple bots, two-way conversations, broadcasts, channel posting (image + text).
- Analytics — funnel, per-source conversion, account health, campaign/A-B results, UTM attribution, referrals.
- Full anti-ban system — rotation, warmup, per-account caps, randomized delays, device fingerprinting, message spinning, flood handling, auto-quarantine.
- Proxy pool (bulk paste, auto-assign, health checks) with optional no-proxy per account.
- Fully customizable Settings, dark/light theme, responsive design.
- Self-hosted via Docker on Ubuntu VPS or Windows, accessible securely over the internet.

**Credits**

Developed by **Jahirul Islam** — [https://jahirulislam.info/](https://jahirulislam.info/)

---

## 13. Build Progress Tracker

Tick each item as it is completed. (Spec/design is done; code phases are pending build.)

**Specification & design**

- [x] Project scope & feature set defined
- [x] Tech stack chosen (FastAPI + React + Postgres + Celery/Redis + Docker)
- [x] Architecture & repo layout
- [x] Database schema
- [x] Anti-ban system spec + config
- [x] UI design (dark/light, card dashboard, three-pane chat, voice, mobile-friendly)
- [x] Full menu map (14 screens)

**Build phases (code)**

- [x] Phase 0 — Foundation (Docker, scaffold, health endpoint)
- [x] Phase 1 — Auth & staff/RBAC
- [x] Phase 2 — Account manager & login (QR/phone/API)
- [x] Phase 3 — Account health & manual status
- [ ] Phase 4 — Warmup
- [ ] Phase 5 — Contacts & CRM pipeline
- [ ] Phase 6 — Unified live inbox
- [ ] Phase 7 — Sender engine + anti-ban
- [ ] Phase 8 — Groups & Channels ("Add members")
- [ ] Phase 9 — Campaigns + drip + A/B
- [ ] Phase 10 — Multi-bot console
- [ ] Phase 11 — Dashboard, analytics + referral
- [ ] Phase 12 — Hardening & deploy
- [ ] Future — Telegram Mini App + Stars (optional)

---

## 14. Activity Log

Append-only record of updates (newest at the bottom).

- **2026-07-14** — v1.0 specification created: scope, tech stack, architecture, repo layout, DB schema, anti-ban system, config, UI screens, roles, phased build plan, deployment.
- **2026-07-14** — Settings made the control center; proxy pool (bulk paste + auto-assign); system-monitoring Dashboard added; phone + username lead support; removed out-of-scope section.
- **2026-07-14** — Warmup screen defined (external partners, group joins, chit-chat templates); Accounts screen (manual status, health tools).
- **2026-07-14** — Unified multi-account Inbox (filters, statuses, bulk actions, campaign-in-thread); Groups & Channels "Add members"; Contacts (CSV/Excel, direct message, already-in-group tag); name-optional contacts.
- **2026-07-14** — Multi-bot management (host multiple bots by token, two-way conversations); schema tables added.
- **2026-07-14** — UI design language: dark/light themes, card dashboard, three-pane chat, voice messages.
- **2026-07-14** — Theme toggle on Dashboard; mobile-friendly responsive design; About screen + §12 About the CRM (credit: Jahirul Islam).
- **2026-07-14 15:05 UTC** — Added Build Progress Tracker (§13) and Activity Log (§14) to this document.
- **2026-07-14** — **Phase 0 (Foundation) built & verified.** Scaffolded the repo per §4: `backend/` (`app/` with config, `db/` + Alembic, `auth`/`schemas`/`services` packages, `api/health.py`; `engine/` Telegram-service heartbeat placeholder; `worker/` Celery app + tasks; `tests/`), `frontend/` (React + Vite + TypeScript, dark/light health-probe landing page), and `sessions/`. Added `docker-compose.yml` (postgres, redis, backend, worker, beat, engine, frontend, caddy) + `docker-compose.prod.yml`, `.env`/`.env.example`, `Caddyfile`, `.gitignore`, `README.md`. Base FastAPI app exposes `/health` and `/health/ready`. **Verified:** `/health` returns HTTP 200 via both uvicorn (real server) and TestClient; 3 pytest tests pass; frontend builds cleanly (`tsc --noEmit` + `vite build`). Note: Docker is not installed on this dev machine, so `docker compose up` was not executed locally — services were verified by running them directly.
- **2026-07-14** — **Phase 1 (Auth & staff/RBAC) built & verified.** DB models `users` (email, password_hash, full_name, role, theme, is_active, created_at, last_login) and `events` (audit log), with Alembic migration `0001_users_and_events`. Auth: bcrypt password hashing, JWT access+refresh (python-jose), `get_current_user` + `require_roles` RBAC guards. API: `/api/auth/login`, `/api/auth/refresh`, `/api/auth/me` (GET/PATCH incl. per-user theme), admin-only `/api/users` CRUD (create/list/get/update/deactivate, self-deactivation blocked), admin-only `/api/audit`. Bootstrap admin via `python -m app.cli ensure-admin` (wired into the backend container startup: `alembic upgrade head && ensure-admin && uvicorn`). Added a 12-factor `DATABASE_URL` override to config. Frontend: React Router with `ProtectedRoute` (+ role guard), zustand auth store with token refresh & localStorage persistence, typed API client, Login page, app shell (icon sidebar, topbar, theme toggle, logout), Dashboard, and admin-only Staff page. **Verified:** 14 pytest tests pass (login, RBAC 403s, refresh, duplicate-email 409, deactivation, self-deactivation 400, audit log); Alembic migration applies + reverses on SQLite; frontend builds clean; **full browser E2E** — admin logs in, creates a manager via the UI, manager login hides Staff nav + Admin card, direct `/staff` URL redirects the manager away, and the theme toggle switches light/dark and persists. No console errors.
- **2026-07-14** — **Phase 2 (Account manager & login) built & verified.** DB models `accounts` and `proxies` (Alembic `0002_accounts_and_proxies`). **Telegram Engine Service** rebuilt as an internal FastAPI (port 9100, private network only) that owns all Telethon clients: `engine/manager.py` (SessionManager — QR login with background watcher + 2FA, phone send-code/sign-in, session-string import→file session, start/status/logout, file sessions under `sessions/` for restart persistence), `engine/proxy.py` (proxy→python-socks tuple), `engine/app.py` + `engine/schemas.py`. Backend: `engine_client.py` (httpx to engine; the API never opens Telethon directly, per the design rule), `app/services/{accounts,proxies}.py` (proxy string parser for `host:port` / `host:port:user:pass` / `scheme://user:pass@host:port`, bulk import + dedupe, auto-assign one free healthy proxy per account), admin/manager `/api/accounts` (CRUD, `/status`, `/reconnect`, QR/phone/session login, logout) and `/api/proxies` (list, import). Frontend: **Accounts** page (list + status badges, add-account, proxy-pool bulk paste), `AccountLoginModal` (QR via `qrcode.react`, phone-code, session-string), nav + route (admin/manager). **Verified:** 34 pytest tests pass (account CRUD, proxy parse unit tests, dedupe incl. intra-batch, auto-assign, RBAC 403, engine delegation mocked, engine-unreachable handling); Alembic `0002` applies + reverses on SQLite; engine app boots + `/health` + proxy conversion correct; frontend builds; **full browser E2E** — imported proxies (3 ok, 1 invalid), created an account with a proxy auto-assigned (pool free-count decremented), opened the login modal (QR/phone/session), and confirmed the **backend→engine round-trip** both when the engine is down (graceful "engine unavailable") and up (engine returns its 400 "API ID/HASH not configured"). Not live-tested: a real QR/phone Telegram login (needs valid API ID/HASH + a phone/scan + Telegram network); the code path is complete and the HTTP contract is verified end-to-end.
- **2026-07-14** — **Phase 3 (Account health & manual status) built & verified.** Engine `engine/health.py`: pure `classify_spambot_reply` (clean/limited/banned/unknown) + Telethon ops `spam_check` (via @SpamBot conversation), `ban_check` (authorized/deactivated detection), best-effort `request_unspam`/`request_unfreeze`; wired into `SessionManager` (authorized-client guard) and the engine API (`/clients/{id}/health/{spam-check,ban-check,unspam,unfreeze}`). Backend: `engine_client` health calls; `/api/accounts/{id}/health/*` endpoints + manual override `PATCH /api/accounts/{id}/status`; **auto-quarantine hook** — a `limited`/`banned` spam-check (when `auto_quarantine_on_warning`) sets status to quarantined/banned and logs an `account.quarantine` event; ban-check `banned`→banned, `unauthorized`→logged_out; `spam_state` persisted; config flag `AUTO_QUARANTINE_ON_WARNING`. Frontend: Accounts spam-state column + `AccountHealthModal` (spam/ban check, unspam/unfreeze, manual status override). **Verified:** 51 pytest tests (9 classifier cases + 8 health/override incl. limited→auto-quarantine, ban→banned, unauthorized→logged_out, login-required 400, invalid-status 422, agent 403); engine boots with health routes; frontend builds; **full browser E2E with a stub engine** — ran Spam check on a logged-in account → "limited" → account auto-quarantined (status badge flipped to quarantined, spam badge to limited) → then manually overridden back to active. No console errors. Not live-tested: real @SpamBot dialog (needs a live authorized account).
