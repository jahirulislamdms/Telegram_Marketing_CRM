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
- [x] Phase 4 — Warmup
- [x] Phase 5 — Contacts & CRM pipeline
- [x] Phase 6 — Unified live inbox
- [x] Phase 7 — Sender engine + anti-ban
- [x] Phase 8 — Groups & Channels ("Add members")
- [x] Phase 9 — Campaigns + drip + A/B
- [x] Phase 10 — Multi-bot console
- [x] Phase 11 — Dashboard, analytics + referral
- [x] Phase 12 — Hardening & deploy
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
- **2026-07-14** — **Phase 4 (Warmup) built & verified.** Models `warmup_runs` (name, status, `stages`/`groups`/`messages` JSON, delays), `warmup_participants` (per-account stage, actions_today, day_key, joined, status), `warmup_partners` (external, no login) — Alembic `0003`. Engine `engine/actions.py`: `join_chat` (public `JoinChannelRequest` + private `ImportChatInviteRequest`, already-participant tolerated) and `send_dm`, wired into `SessionManager` + engine API `/clients/{id}/warmup/{join,send}`. Service `app/services/warmup.py`: staged-ramp orchestration — `run_tick(db, run, now, execute)` resets daily counters, **advances stages on schedule** (elapsed ≥ stage.days) with completion→account reactivation, and performs **one paced action per eligible participant** (join an un-joined group, else chit-chat a fleet peer's phone or a partner), capped by the current stage's `max_actions` and gated by `min_delay_seconds` (staggering). API `app/api/warmup.py` (Admin/Manager): run CRUD, add/remove participants, add partners, start/pause/stop, and a `tick` endpoint (also driven by a Celery beat task `warmup.tick` every 5 min). Frontend: **Warmup** page (run list, create run, per-run detail with participants + `stage n/3` progress, external partners, Start/Pause/Resume/Stop, Run tick). **Verified:** 57 pytest tests (6 new: stage advancement on a simulated clock, final-stage completion→account active, join-then-chit-chat action selection, daily-cap enforcement, full API workflow, agent 403); Alembic `0003` up/down on SQLite; engine boots with warmup routes; frontend builds; **full browser E2E with a stub engine** — created a run (default stages 3d×2→4d×5→5d×12), added 2 fleet accounts + an external partner, started it, and a tick performed 2 join actions (each account's actions-today → 1), then paused. No console errors. Not live-tested: real group joins / message sends (need live authorized accounts + Telegram network).
- **2026-07-14** — **Phase 5 (Contacts & CRM pipeline) built & verified.** Model `contacts` (name optional with display-label fallback name→@username→phone; `lead_type` phone/username; `telegram_user_id`; `resolution_status`; `stage`; `consent`/`opted_out`; `assigned_account_id`/`assigned_agent_id`; `utm`/`tags` JSON) — Alembic `0004`. Import: `services/contacts.py` parses **CSV and Excel** (openpyxl), dedupes on phone/username (incl. intra-batch), **rejects rows without consent**, counts invalid; `GET /api/contacts/import-template` serves the §5.1 example. Resolution: engine `engine/resolve.py` (`resolve_username` via get_entity, `resolve_phone` via ImportContacts) + `/clients/{id}/resolve/{username,phone}`; backend picks a logged-in account and updates `telegram_user_id`+status. Messaging: engine `/clients/{id}/message`; `POST /api/contacts/{id}/message` with the **consent guardrail** (403 if not consented or opted-out), auto-advances new→contacted and stamps `last_contacted_at`. CRUD + bulk (stage/assign/delete/resolve); **agents see/act on their own assigned contacts only** (managers/admins all); import/bulk are Manager/Admin. Frontend: **Contacts** page (import + template download, add contact, search/stage filter, per-row resolve/message, bulk select→stage/delete) with a message modal (pick a logged-in account), and a **Pipeline** Kanban (columns per stage, move via card select). **Verified:** 71 pytest tests (14 new: CSV import dedupe+consent, Excel import, template, create/label/stage transitions, identifier-required 422, resolve, message + consent/opt-out 403s, agent ownership 403s); Alembic `0004` up/down on SQLite; engine boots with resolve/message routes; frontend builds; **full browser E2E with a stub engine** — added a username contact, resolved it (pending→resolved), messaged it from a chosen account (new→contacted), then moved it Contacted→Customer on the Kanban. No console errors. Not live-tested: real username/phone resolution and message delivery (need live authorized accounts).
- **2026-07-14** — **Phase 6 (Unified live inbox) built & verified.** Models `conversations` (contact/account/peer, unread_count, status, last-message preview) + `messages` (direction in/out, type text/image/voice/link, body, media_ref, tg id, status) — Alembic `0005`. Realtime: `app/realtime.py` WebSocket `ConnectionManager` + best-effort Redis pub/sub bridge that **falls back to in-process broadcast** when Redis is down; `/ws/inbox` (token via query param). Engine `engine/listener.py` registers a Telethon `NewMessage` handler on each authorized client and publishes private incoming messages to Redis `inbox:incoming`; backend `inbox_consumer.py` subscribes, persists, and fans out. Service `services/inbox.py`: record incoming (links contact by telegram id/username, advances contacted→replied, **auto-honors opt-out** replies → contact opted_out), record outgoing, list/thread/mark-read/set-status (syncs the linked contact's pipeline stage), bulk. Engine `send_file` for images. API `/api/inbox/*`: list conversations (agent-scoped to own), thread, read, PATCH status, **send reply** (text/link, image-by-URL) via the conversation's account, bulk read/status, and a dev `simulate-incoming` that drives the same record+broadcast path. Frontend: **Inbox** three-pane page (conversation list · chat thread · contact profile) with a `useInboxSocket` hook for live updates, composer, and per-conversation status. **Verified:** 81 pytest tests (10 new incl. a WebSocket receive test, incoming→conversation, reply records outgoing, link-type detection, opt-out honored, contact-link + stage advance, bulk); Alembic `0005` up/down on SQLite; engine boots with send-file route; frontend builds; **full browser E2E** (in-process broadcast, Redis-down) — simulated an incoming message that appeared **live** in the list, opened the thread, sent a reply that appeared live via the WS broadcast, and changed the conversation status to customer. No console errors. Not live-tested: real Telegram incoming (needs the engine listener + Redis + a live account).
- **2026-07-14** — **Phase 7 (Sender engine + anti-ban) built & verified.** Models `send_jobs` (template, include_link/link_url/suppress_link_first, active window, status, last_account_id) + `send_targets` (per-contact status/rendered_body/account/error) — Alembic `0006`. Anti-ban helpers `worker/antiban/`: `spintax.py` (`spin` — nested `{a|b}` variants) and `pacing.py` (`rotate` round-robin never-consecutive, `under_daily_cap`, `delay_ok`, `in_window`). Service `services/sender.py`: `render_message` (spintax + **suppress link on first contact**), job CRUD, `add_targets` (**consented, non-opted-out only**, deduped), and `run_tick(now, execute)` — eligible = active+logged-in accounts filtered by daily cap / active-hour window / min-delay; rotated one send per usable account; on send **auto-advances contact new→contacted**; on a flood/peer-flood/ban/engine warning it **quarantines the account and auto-pauses the job**. Engine `send_dm`/`send_file` now return `{sent, error}` on flood/peer-flood/ban (not raised) so all callers back off; contacts/inbox/warmup send-callers updated. `build_executor` sends via the engine and **lands the message in the inbox thread** (conversation + outgoing message + WS broadcast); shared by the API tick and the Celery `sender.tick` (beat every 60s). API `/api/sender/*` (Admin/Manager): job CRUD, add targets, start/pause/stop, tick. Frontend: **Sender** page (create job w/ spintax + link options, add targets by source, start/pause/resume/stop, run tick, per-target status + which account sent). **Verified:** 95 pytest tests (14 new: spintax incl. nested, rotate/cap/delay/window, suppress-link-first, service rotation across accounts + cap enforcement, consent-only targets, send-lands-in-inbox + stage advance, **flood auto-pause + quarantine**, tick-not-running 400, agent 403); Alembic `0006` up/down on SQLite; frontend builds; **full browser E2E with a stub engine** — created a spintax job, added 3 consented contacts, started it, and a tick sent 2 (Alpha via account #1, Beta via account #2 — **rotation**), rendered spintax with no braces, left the 3rd queued (**pacing**), and both sends **appeared in the inbox** as outgoing messages with the contact advanced to "contacted". No console errors. Not live-tested: real Telegram delivery / real FloodWait (need live accounts).
- **2026-07-14** — **Phase 8 (Groups & Channels "Add members") built & verified.** Models `destinations` (title, link, tg_entity_id, type group/channel, invite_link, added_via) + `group_memberships` (contact_id, destination_id, state pending/added/invited/joined/failed, method, account_id, error; unique(contact,destination)) — Alembic `0007`. Engine `actions.py`: `resolve_destination` (get_entity → id/title/type) and `add_member` — **direct-add** (`InviteToChannelRequest` for channels, `AddChatUserRequest` for basic groups) with **automatic invite-link fallback** (`ExportChatInviteRequest` → DM the link) on any non-flood error; flood/peer-flood returned as `{state:failed,error}`. Engine routes `/clients/{id}/destination/{resolve,add}` + `engine_client`. Service `services/destinations.py`: register (resolves via a logged-in account, stores unresolved if the engine is down), `add_members` (**consented, non-opted-out contacts** + typed identifiers find-or-created; **excludes contacts already in the destination**), `run_add_tick` (eligible accounts by cap/delay, rotated one add per account, on flood **quarantines the account and stops** leaving memberships pending), `already_member_contact_ids` / `contact_destination_ids`. Contacts list gains `in_destination` / `not_in_destination` filters (the exclusion). API `/api/destinations/*` (Admin/Manager). Frontend: **Groups & Channels** page (register destination, build member list from a consented-contact picker + typed identifiers, run add, results table with state/method/account, **already-in-group contacts tagged and disabled**). **Verified:** 104 pytest tests (9 new: register resolved/unresolved, consent+typed member queueing, direct-add tick, invite-fallback tick, **already-member exclusion + in/not-in-destination filters**, flood quarantine, tick-requires-resolved 400, agent 403); Alembic `0007` up/down on SQLite; frontend builds; **full browser E2E with a stub engine** — registered a destination (resolved to "VIP Customers"/group), queued 2 consented contacts, ran add → Alpha **added via direct_add** by account #1 and then shown as **"in group" (excluded)**. No console errors. Not live-tested: real direct-add / invite (need live accounts + a real group).
- **2026-07-14** — **Phase 9 (Campaigns + drip + A/B) built & verified.** Models `templates` (name, body spintax, include_link/link_url, `variant_group` + `variant_label` for A/B), `campaigns` (action message/invite/add, destination_id, `segment` JSON, `steps` JSON drip list of {offset_hours, variant_group}, ab_test, status, last_account_id), `campaign_targets` (contact, step, template_id, account, scheduled_at, sent_at, result queued/sent/replied/joined/failed/skipped; unique(campaign,contact,step)) — Alembic `0008`. Service `services/campaigns.py`: template CRUD, **segment builder** (consent guardrail + source/stage/tag + **exclude_in_destination** reusing `already_member_contact_ids`), `materialize_targets` (per-contact × per-step, **A/B split** `variants[contact_id % n]` when ab_test, **scheduled at started_at + offset_hours** for drip), start/pause/stop, `run_tick` (eligible accounts by cap/delay/rotation, processes **due** queued targets, dispatches by action — **message** → engine send + **lands in the inbox** + contact new→contacted; **add/invite** → `add_member` + records a group_membership; flood → quarantine + pause), and `ab_report` (per-variant queued/sent/joined/failed + replied proxy from contact stage). API `/api/templates` + `/api/campaigns/*` (Admin/Manager) with validation (add/invite need a destination, message steps need a variant_group). Celery `campaigns.tick` (beat every 60s). Frontend: **Campaigns** page (template A/B editor, campaign builder with segment/action/variant-group/A-B/drip-offsets/exclude-in-group, per-campaign controls, **A/B results table**). **Verified:** 113 pytest tests (9 new: template A/B, A/B materialization split, drip multi-step scheduling, **segment exclude-already-in-destination**, message tick sends+inbox+A/B report, add tick creates membership, flood pause, message-requires-variant-group 400, agent 403); Alembic `0008` up/down on SQLite; frontend builds; **full browser E2E with a stub engine** — created A/B templates (spring_promo A/B), a source-segmented A/B campaign, started it (**4 targets materialized, split across variants**), ran a tick (2 accounts → 2 sent) and the **A/B results showed Variant A = 1 sent, Variant B = 1 sent**. No console errors. Not live-tested: real delivery.
- **2026-07-15** — **Phase 11 (Dashboard, analytics + referral) built & verified.** Model `referrals` (referrer_subscriber_id → bot_subscribers, unique `invite_code`, `invited_count`, `rewarded`) — Alembic `0010`. Service `services/referrals.py`: `get_or_create_referral` (one per subscriber, random `token_hex` code), `record_referral`/`maybe_record_from_payload` (credit a `ref_<code>` bot-start payload), `set_rewarded`, and a `leaderboard` (referrals ⋈ subscriber ⋈ bot, by invited_count). Service `services/analytics.py`: **system-monitoring** `dashboard_snapshot` (account counts by status, today's sends-vs-caps, sender+campaign **queue depth**, proxy-pool health ok/dead/assigned/free, **throughput** = out-messages 24h/1h [time-windowed **in Python** for SQLite/PG portability], **running campaigns** with per-campaign progress, recent quarantine/flood **events**) plus marketing analytics — `funnel` (cumulative reached counts contacted→customer + conversion %), `per_source_conversion`, `per_account_health`, `campaign_summary` (per-campaign A/B rollup), and `utm_attribution` (bot subscribers grouped by UTM deep-link source, with joined/customer conversions). Schemas `schemas/analytics.py` + API `api/analytics.py` (Admin/Manager): `GET /api/analytics/dashboard`, `POST …/dashboard/broadcast` (computes a snapshot and pushes a `dashboard` event over the inbox WS — reuses `realtime.publish`), `GET /api/analytics` (overview), and referral endpoints (`GET /referrals` leaderboard, `POST /referrals` create-for-subscriber → deep-link, `POST /referrals/record`, `POST /referrals/{id}/reward`). Celery beat `analytics.dashboard_tick` (every 15s) broadcasts the snapshot. Frontend: **Dashboard** rebuilt as live system monitoring (account-health tiles, throughput, queue, caps progress bar, proxy pool, running-campaign progress, error feed; subscribes to the inbox WS for `dashboard` push → **Live** indicator, with a 15s poll fallback; agents get a simplified home) and a new **Analytics** page (funnel bars, per-source table, campaign/A-B table, UTM table, referral leaderboard with create-link / record / reward tools) + nav + route (Admin/Manager). **Verified:** 131 pytest tests (10 new: dashboard shape, account-count reflection, **`dashboard` WebSocket broadcast**, funnel + per-source conversion math, per-account health, UTM attribution, referral create/record/reward/leaderboard incl. `ref_`-prefixed codes + idempotent create, unknown-code/subscriber 404s, agent 403); Alembic `0010` up/down on SQLite; frontend builds (`tsc --noEmit` + vite); **full browser E2E with a seeded SQLite DB** (in-process WS, Redis-down) — logged in, the **Dashboard showed live system state** (4 accounts: 2 active/1 warming/1 quarantined, sends 21/95 caps = 22.1%, queue 2, proxy pool 3 ok/1 dead/1 assigned/3 free, running "Spring Promo" 2/4, a quarantine event), a `dashboard` broadcast flipped the indicator to **Live** and refreshed the snapshot, and **Analytics** showed the funnel (28.6% contacted→customer), per-source conversion (online_store 16.7% / offline_store 33.3%), the A/B campaign row (4 targets, 2 sent), UTM attribution (instagram 2 / direct 1), and the **referral leaderboard** — then a UI **record** bumped the top referrer 3→4 invites and **Reward** flipped it to ✓. No console errors. Not live-tested: real Celery-beat push (needs Redis + worker) and real UTM/referral traffic from live bots.
- **2026-07-14** — **Phase 10 (Multi-bot console) built & verified.** Models `bots`, `bot_subscribers`, `bot_conversations`, `bot_messages` (Alembic `0009`). Engine hosts **aiogram v3** bots alongside Telethon: `engine/bots_manager.py` (`BotManager` — add-by-token start/stop polling in a background task, `/start` handler captures subscriber + **UTM deep-link payload** and message handler publishes to Redis `bot:incoming`/`bot:start`; send/post/get_me); engine routes `/bots/{start,stop,info,send,post}` (aiogram lazy-imported so the engine boots without it) + `engine_client`. Backend: `services/bots.py` (CRUD, start/stop, subscriber upsert, bot inbox get/thread/reply, **broadcast** to subscribers, **post to channel** text+image, `deep_link`), `bot_consumer.py` (Redis `bot:incoming`/`bot:start` → DB → WS `bot_message`), `/api/bots/*` (Admin/Manager: list/add/start/stop/remove, subscribers, conversations/thread/read/reply, send/post/broadcast, deep-link, dev simulate-incoming). Reuses the realtime WS (`/ws/inbox`) with a `bot_message` event type. Frontend: **Bots** page (add by token, list, start/stop/remove, counts, opt-in deep-link, **bot inbox** two-pane with live updates + reply, post-to-channel, broadcast). **Verified:** 121 pytest tests (8 new: add/start/stop, incoming→subscriber+conversation+UTM, reply via bot, broadcast, post-to-channel, deep-link, **WebSocket bot_message**, agent 403); Alembic `0009` up/down on SQLite; engine boots with bot routes; frontend builds; **full browser E2E with a stub engine** — added **two bots from pasted tokens**, started one (running + deep-link), simulated an incoming message that appeared **live** in the bot inbox, **replied** (staff→user), and **posted text+image to a channel** ("Posted to channel."). No console errors. Not live-tested: real BotFather bots / real Telegram delivery.
- **2026-07-15** — **Phase 12 (Hardening & deploy) built & verified — BUILD COMPLETE (all 13 phases 0–12 done).** No DB changes. **API rate limiting:** `app/ratelimit.py` (fixed-window per-client limiter, Redis-backed `INCR`+TTL with a thread-safe in-process fallback) + `app/middleware.py` `RateLimitMiddleware` (limits `/api/*` per client IP — honors `X-Forwarded-For` first hop; **tighter cap on `/api/auth/login|refresh`** for brute-force; exempts `OPTIONS`, `/health`, `/ws`; returns **429 + `Retry-After` + `X-RateLimit-*`**). **Security headers:** `SecurityHeadersMiddleware` (nosniff, `X-Frame-Options: DENY`, Referrer-Policy, Permissions-Policy, HSTS) on every response, plus the same set at the **Caddy** layer (covers the SPA) with `-Server`. Middleware registered before CORS so CORS stays outermost and stamps 429s. **Secrets guard:** `settings.insecure_production_defaults()` + a **startup check that refuses to boot in `ENVIRONMENT=production`** on default `SECRET_KEY`/admin password/DB password/`CORS=*`/`DEBUG`; new CLI `python -m app.cli generate-secret` and `prod-check` (prod compose runs `prod-check` before uvicorn). **Readiness:** `/health/ready` now checks Postgres (required → 503 if down) and Redis (reported, non-fatal). **Backups:** `scripts/backup.sh` (`pg_dump`|gzip + retention prune), `scripts/restore.sh`, `scripts/backup-loop.sh`, and a **`backup` service** in `docker-compose.prod.yml` (nightly, rotates, writes `./backups`). Config knobs added to `app/config.py` + `.env.example` (rate limits, security headers, HSTS, backup interval/retention). **Docs:** new `docs/DEPLOY.md` (Ubuntu VPS + Windows install, DNS/HTTPS, firewall, backup/restore, security checklist, troubleshooting) + README updated. **Verified:** 144 pytest tests (13 new: security headers on 200/401, rate-limit 429 + `Retry-After` + per-IP isolation + allowed-request annotation + `/health` exempt + disabled-by-default passthrough, readiness DB-ok/Redis-down, insecure-defaults + secure-config helper, `generate-secret`/`prod-check` CLI); frontend still builds (no FE changes); compose files YAML-lint clean (prod adds `backup`); backup/restore/loop scripts pass `sh -n`; **live-server verification** (real uvicorn + browser, seeded DB, `REDIS_HOST=127.0.0.1`, login limit=4) — `/health` returned all 5 security headers, `/health/ready` = `{database: ok, redis: down, status: ready}` (200), login **401×4 then 429** with `Retry-After: 53` + `X-RateLimit-*`, a **valid login returned 200**, and the **browser logged in and loaded the live Dashboard** through the middleware with `/api/*` carrying `X-RateLimit-Limit: 240` and no console errors. Not live-tested (no Docker/Redis/Postgres locally): `docker compose up` on a real VPS, Caddy ACME cert issuance, and the scheduled `backup` service run — code/compose/scripts complete and validated.
- **2026-07-16** — **§15.1.a fixed — the "engine 500" on every message send.** Root cause: a peer's numeric Telegram user id was passed to the engine as a *string* (e.g. `"6430475606"`); Telethon reads an all-digit string as a **username** lookup → `ValueError: Cannot find any entity`, surfaced as engine `500` on **every** send (inbox reply, Contacts message, Sender, Campaigns). Fix: `engine/actions.py` new `coerce_target()` converts all-digit ids (incl. a leading `-` for chats/channels) to `int`, while leaving `@usernames`/`+phones` as strings; applied in `send_dm`, `send_file`, and `add_member`. Regression unit tests `tests/test_engine_actions.py` (incl. the exact production id `6430475606`). Verified: **149** pytest pass; engine image rebuilt and **redeployed to the VPS**. First fix of the §15 update phase; local → GitHub → VPS.
- **2026-07-16** — **§15.1.b done — inbound media (image/video/gif/sticker/voice/file) shown from Telegram, never stored on the VPS.** Migration `0011` relaxes the `messages.type` CHECK to allow `video/gif/sticker/audio/file` (portable: PG drop+add, SQLite batch). Engine: `listener.media_info()` classifies a message's media and records `type` + a small JSON `media_ref` (mime/name/size/duration); `actions.download_media()` re-fetches the message and streams the bytes via `msg.download_media(file=bytes)` (nothing written to disk) — reuses `coerce_target` for the peer; new engine route `POST /clients/{id}/download-media` returns the raw bytes. Backend: `engine_client.download_media` (binary), `record_incoming` stores `type`/`media_ref` (+ `[kind]` preview), and **`GET /api/inbox/messages/{id}/media`** streams media on demand (agent-scoped; `inline` for visual media, `attachment` for files; 404 → "media no longer available" when the peer deleted it). Frontend: `MediaAttachment` fetches the media as an **authed blob** (token in header, not URL) → object URL → renders `<img>`/`<video>`/`<audio>`; files download on click; captions still shown. **Verified:** 154 pytest pass (5 new: record media, stream bytes, file-as-attachment, 404 gone, 404 for text); migration `0011` up/down on SQLite; frontend builds; **browser E2E with a stub engine** — an inbound image rendered in the thread (`<img>` with a `blob:` src, `naturalWidth/Height=1`, no console errors). Deployed to the VPS. Note: animated stickers (`.tgs`) render via their static representation; full Lottie is a later nicety.
- **2026-07-16** — **§15.1.c done — send image/video/file/voice from the composer, uploaded straight to Telegram (never stored on the VPS).** Engine: `actions.send_media()` wraps the uploaded bytes in an in-memory `BytesIO` (named so Telethon infers the type) and `client.send_file()`s them with per-kind flags (`voice_note` for voice, `supports_streaming` for video, `force_document` for files), returning the sent `message_id`; `manager.send_media` + engine route `POST /clients/{id}/send-media` (base64 body decoded in-memory). Backend: `engine_client.send_media` (base64 JSON), and **`POST /api/inbox/conversations/{id}/send-media`** — a **multipart upload** (≤25 MB) that forwards the bytes to the engine and records the outgoing message with `type`/`media_ref`/`tg_message_id` (so it re-renders from Telegram via the 15.1.b media endpoint); flood → 502, empty → 400. Frontend: composer gains an **attach** button (image/video/file → kind inferred from mime) and a **voice** button (browser `MediaRecorder` opus → sent as a voice note); `inboxApi.sendMedia` posts multipart with the token in the header. **Verified:** 157 pytest pass (3 new: outbound recorded + re-fetchable, flood 502, empty 400); frontend builds; **browser E2E with a stub engine** — sending an image from the composer produced an **outgoing image bubble** that rendered (`blob:` `<img>`, loaded) with its caption, composer attach/voice buttons present, no console errors. Deployed to the VPS. Caveat: browser voice records opus in a webm/ogg container; sent with `voice_note=True` — if a client is picky it shows as an audio message; server-side transcode is a later nicety.
- **2026-07-16** — **§15.1.d/e/f/g done — inbox UX: peer panel + save-as-contact, multi-account selector, "via account", conversation search.** Migration `0012` adds `conversations.peer_username` (stored normalised — `@` stripped, lowercased — and backfilled on later messages). Backend `services/inbox.py`: `get_or_create_conversation` stores/backfills `peer_username`/`peer_name`; `list_conversations` gains **`account_ids`** (all / one / many — 15.1.e) and **`q`** (searches peer name, peer username, last-message preview, and the linked contact's name/username/phone — 15.1.g); `conversation_dict` now returns **`account_label`** (15.1.f) + `peer_username`; new **`save_peer_as_contact()`** creates a CRM contact from an inbox peer (`consent=true`, `source="inbox"`, `resolution_status=resolved`, stage mirrors the conversation) and links it, reusing an existing contact if one already matches the peer. API: `GET /api/inbox/conversations?account_ids=1,2&q=…` (400 on non-integer ids) and **`POST /api/inbox/conversations/{id}/save-contact`** (400 if already linked / no peer identity; agent-scoped; audit-logged). Frontend **Inbox**: a **searchable multi-account picker** (All accounts / N accounts), a **debounced conversation search**, **"via <account>"** on every list row and in the chat header, and a right-hand **peer panel** (name, @username, Telegram ID, via-account — plus phone/stage/source/consent once linked) with a one-click **"Save as contact"**. **Verified:** 163 pytest pass (6 new: account filter + account_label, non-integer ids 400, search by name and by preview, peer_username normalisation, save-as-contact incl. re-save 400, auto-link for a known contact); migration `0012` up/down on SQLite; frontend builds; **browser E2E** — two accounts with three chats: rows showed "via Sales Alpha/Support Beta", the picker searched ("sup" → Support Beta) and filtering to Sales Alpha narrowed the list to its 2 chats, searching "zebra" left 1, and **Save as contact** flipped the panel from "Sender" to "Contact" and created the contact (`source=inbox`, `consent=true`, `tg=900001`). No console errors. Deployed to the VPS.
- **2026-07-16** — **§15.1.h/i/j done — retention, Archive/Delete, and the Archive folder. §15.1 IS NOW COMPLETE (a–j).** Migration `0013` adds `conversations.archived` (bool, default false, independent of the pipeline status). **Retention (15.1.h):** the CRM is the system of record — the engine listener handles **only** `NewMessage` and deliberately does **not** subscribe to `MessageDeleted`, so a peer deleting on Telegram never removes our rows; the message + text stay and only its media becomes unfetchable (media endpoint 404 → "media no longer available"). This is now documented in `engine/listener.py` and pinned by a regression test. **Archive/Delete (15.1.i):** `set_archived()` + `POST /api/inbox/conversations/{id}/archive` `{archived}` (anyone with access; history kept either way); `delete_conversation()` + `DELETE /api/inbox/conversations/{id}` — **Admin/Manager-only** and audit-logged, deleting our copy + its messages explicitly (not via FK cascade, which SQLite doesn't enforce) and never touching the peer's Telegram. **Archive folder (15.1.j):** `list_conversations(archived=…)` — the main inbox shows only non-archived; `?archived=true` is the folder. Frontend: **Inbox | Archive** tabs, and thread-header **Archive/Unarchive** + **Delete** (with a confirm that spells out it only removes our copy). **Verified:** 167 pytest pass (4 new: archive→folder→unarchive incl. history kept, delete removes conversation+messages, agent 403 on delete, retention after a peer-side delete); migration `0013` up/down on SQLite; frontend builds; **browser E2E** — archived a chat (left the inbox, appeared under Archive), unarchived it back, and deleted one (confirm shown and honoured, row gone). No console errors. Deployed to the VPS.
- **2026-07-16** — **§15.2 done — Backup & Restore center. §15 (15.1 + 15.2) IS NOW COMPLETE.** Placed under a new **Settings** nav option (Admin only) per the note on §15.2. Migration `0014` adds an `app_settings` key/value store (JSONB on PG, JSON on SQLite) for UI-editable settings that must survive restarts. `services/backup.py`: a backup is one `.tar.gz` in `BACKUP_DIR` plus a small `.meta.json` sidecar (so listing never opens the archive), containing `manifest.json` + the **selected scope** — `database` (`pg_dump --clean --if-exists --no-owner` on PG; a copy of the SQLite file in dev/tests, so the same code path is exercised by the suite), `sessions` (Telethon session files, so restored accounts stay logged in), `settings` (`app_settings` rows + **non-secret** tunables — raw `.env` secrets are deliberately never archived). Default scope = everything. `restore_backup()` extracts (rejecting unsafe members), restores sessions/settings then the database last, and is disruptive by design; `prune_backups()` keeps the newest `BACKUP_KEEP_LAST` (5); `resolve_archive()` is the **path-traversal guard** for download/delete/restore. API `api/backups.py` — **Admin-only**, audit-logged: `GET/POST /api/backups`, `GET /api/backups/{name}/download` (authed blob), `DELETE`, `POST …/restore`, and `GET/PUT /api/backups/settings` (on/off + every-N-days + scope). Celery beat `backup.auto_tick` runs hourly and honors the **UI-editable** schedule, so changing it needs no beat restart. **Infra:** the backend image now installs `postgresql-client` (it had **no `pg_dump`**), and the backend/worker/beat now mount `./sessions` and `./backups` (the backend previously could not see the real session files at all) — plus the long-standing `${CADDY_SITE_ADDRESS::80}` compose interpolation bug is finally **fixed upstream** (it was only patched on the VPS). **Verified:** 181 pytest pass (14 new: all-scope + selected-scope archives, prune-to-5 incl. sidecar, download gzip, delete, **4 path-traversal/bad-name cases**, restore round-trip restoring sessions+settings, 404s, settings defaults/update/validation, `is_due`, manager-403 RBAC); migration `0014` up/down on SQLite; frontend builds; compose YAML lints; **browser E2E** — created a backup from the UI (all three scopes checked by default → 8 KB archive that really contained `database.sqlite`, `sessions/9.session` with intact bytes, `settings.json`, manifest), enabled auto-backup and changed it to every 3 days (persisted server-side), and deleted it (confirm honoured; archive + sidecar gone from disk). No console errors. Deployed to the VPS.
- **2026-07-16** — **§15.2.f added — load a backup from a previously downloaded file.** Purely **additive** (no existing function changed): `backup.save_uploaded_backup()` validates the upload is a real CRM archive (`manifest.json` present + sane scope) **before** accepting it, enforces `BACKUP_MAX_UPLOAD_MB` (default 500), stores it under a fresh collision-safe name so it sorts newest and **is never pruned away** (upload deliberately does not prune), and records the archive's **original** creation time for display; restoring it then uses the **existing** restore flow untouched. New Admin-only, audit-logged `POST /api/backups/upload` (multipart). `BackupOut` gains two optional fields (`original_created_at`, `uploaded`) — additive, so existing archives still serialise. Frontend: a **"Load a backup file"** card in Settings (file picker → validated → listed), and the list marks loaded archives with an **uploaded** badge plus "made \<original time\>". **Verified:** 187 pytest pass (6 new: download→delete→re-upload→restore round-trip with the original time preserved, reject non-archive, reject tar.gz without a manifest, reject empty/oversized, upload survives `keep_last=1`, manager-403); frontend builds; **browser E2E** — the card renders, and a created backup was downloaded, deleted server-side, loaded back from the file (201, `uploaded=true`, original time matched) and **restored** (sessions+settings+database), showing the uploaded badge. No console errors. **Not yet deployed to the VPS** (awaiting an explicit deploy request). Note for deploy: nginx's `client_max_body_size 25m` on the CRM site caps uploads — raise it if archives exceed that.
- **2026-07-16** — **Bug fix: could not message a phone contact (engine 500) — a follow-up to §15.1.a.** Sending to a username contact worked but a **phone** contact failed everywhere (Contacts/Inbox/Sender/Campaigns) with `engine error 500`. Root cause: `message_target()` returned the raw phone, and a phone **saved without a leading `+`** (e.g. `8801646562267`) is indistinguishable from a Telegram user id — so `coerce_target` made it an `int`, Telethon read it as `PeerUser(user_id=8801646562267)`, and `send_message` raised `Could not find the input entity` (uncaught → 500). Telegram cannot message a raw phone at all; it must first be **imported** to resolve it to a user. Fix (three parts): (1) engine `actions.resolve_for_send()` — a `+phone` target is now imported via `ImportContactsRequest` to get the user entity before sending (mirrors the existing phone-lead resolver); reused by `send_dm`/`send_file`/`send_media`; a phone with no Telegram account returns a clean `{sent: False, error: "no Telegram account …"}`. (2) those three now also catch **any** send failure and return it instead of raising, so the engine **never 500s** on a bad recipient. (3) phones are made unambiguous: `normalize_phone()` always keeps a leading `+`, `message_target()` prefixes `+` defensively, and **migration `0015`** back-fills a `+` onto existing digit-only phones (portable `'+' || phone` update). **Verified:** 194 pytest pass (10 new: `send_dm` imports+sends a `+phone` to the resolved user, no-Telegram → clean error, generic failure never raises, numeric id passes through, `send_media` resolves a phone, `resolve_for_send` passthrough, `normalize_phone` adds `+`, and the Contacts message API sends a `+`-prefixed target); migration `0015` up/down on SQLite verified to rewrite `8801646562267 → +8801646562267` while leaving `+14155550123` untouched. Engine-only Telethon `ImportContacts` not live-tested locally (needs a real account). **Not yet deployed to the VPS** (awaiting an explicit deploy request).
- **2026-07-16** — **Bug fix (part 2): phone contact sent from one account but not the others.** Live logs showed two variants — `Cannot find any entity corresponding to "+8801646562267"` (unresolved phone) **and** `Could not find the input entity for PeerUser(user_id=855963265073)` (a **resolved** contact). Root cause of the second: a Telegram entity's **access-hash is per-account (per-session)** — a cached `telegram_user_id` can only be messaged by the one account that resolved it; sending it from any other account fails. That's why "one account worked, the rest 500'd" (the working account is the one that had resolved/imported the lead). Not privacy — session-local entity caching. Fix: a shared `contacts.send_identifier(contact)` now **prefers a re-resolvable identifier** — `@username` (publicly resolvable by any account) then `+phone` (imported per-account by the part-1 fix) — and only falls back to the numeric id when there's neither. Applied to the Contacts message path (`message_target` is now an alias), **`sender.build_executor`**, and **`campaigns._execute_target`** (both previously preferred the id, so account rotation hit the same wall). **Verified:** 195 pytest pass (1 new: `send_identifier` ordering — a resolved phone lead still targets `+phone`, `@username` beats the id, bare phone gains `+`, id only as last resort); no circular imports. **Not yet deployed to the VPS.**
- **2026-07-20** — **§15.3 done — Contacts Module UX & Management Upgrade.** A non-breaking modernization of the Contacts page: the pipeline **stage system is untouched** (same six values, same "Set stage" behaviour) and Pipeline/Inbox/Campaigns/Analytics/Sender were not modified. **Backend:** migration `0016` adds a nullable `contacts.notes` (Text). `services/contacts.py` — new `DuplicateContact` + `find_conflict()` (phone & username unique), `create_contact` now 409s on a conflict, a new `edit_contact()` (normalises phone/username, enforces uniqueness excluding self, keeps `lead_type` in sync, allows clearing a field), `import_contacts()` **now UPDATES a matched contact instead of skipping the duplicate** (returns `imported`/`updated`/`rejected_no_consent`/`invalid`/`errors`/`total`, wraps each row so one bad row can't abort the batch), `count_contacts()` + `list_contacts()` extended with `lead_type`/`consent`/`limit`/`offset` filters and search over **source** too, and CSV/XLSX exporters (`contacts_to_csv`/`contacts_to_xlsx`, columns name/phone/username/source/stage/resolution/consent/created_at). `api/contacts.py` — `GET /api/contacts` sets an **`X-Total-Count`** header (unpaginated total) so lists stay a plain array (Pipeline/Groups, which call it without `limit`, are unaffected); new `GET /api/contacts/export` (csv|xlsx; `ids=` selected, else filtered), `POST /api/contacts/bulk/consent` and `POST /api/contacts/bulk/unresolve`; PATCH routes identity fields through `edit_contact` (409/422) while stage/consent/assignment keep the old generic path. `ContactOut`/`ContactCreate`/`ContactUpdate` gain `notes`; `ContactUpdate` gains editable `phone`/`username`; `ImportResult` gains `updated`/`errors`. **Frontend:** Contacts page rebuilt — modern table (initials avatar, Name + @username + Phone shown together and never hidden, rounded stage/resolution badges, sticky header, hover, row-select highlight), debounced search + combining filters (stage/type/resolution/consent/source with a datalist), quick-action **icon** buttons (💬 Message / 🔄 Resolve / ✏️ Edit / 🗑️ Delete) with tooltips, an **Edit Contact** modal (`ContactEditModal.tsx`; name/phone/username/source/stage/consent/notes; ✏️ or double-click; saves in place), a **Bulk actions** dropdown (change stage, mark/remove consent, resolve/unresolve, export selected, delete-with-confirm) with select-page / select-all-matching / clear, an **Export ▾** menu (all/filtered · CSV/Excel), an import summary chip row, **pagination** (rows 10/25/50/100 + "Showing X–Y of N"), an **empty state**, and **loading skeletons**. `api/client.ts` adds `listPage` (reads `X-Total-Count`), `exportFile`, `bulkConsent`/`bulkResolve`/`bulkUnresolve`, and `notes`. **Verified:** 203 pytest pass (8 new: dup phone/username 409, import updates-not-duplicates, edit fields incl. notes, edit-into-duplicate 409, bulk consent+unresolve, CSV+XLSX export, pagination + total header); migration `0016` up/down on SQLite; `npm run build` (tsc clean); **browser E2E** against a 30-contact seed — rendered the modern list with avatars + "Showing 1–25 of 30", filtered to stage=customer (5), edited a contact's name+notes (persisted via API incl. `notes`), got "Phone number already exists." on a duplicate add, bulk-moved 5 customers → replied (list emptied → empty state), and exported CSV; no console errors. **Deployed to the VPS 2026-07-20** (backend files synced + `alembic upgrade head` to `0016` + `backend`/`worker`/`beat` recreated + SPA rebuilt). **Pushed to GitHub and the VPS re-synced via `git fetch && git reset --hard origin/main` on 2026-07-20** — login (Telethon `sessions/1,4,5.session`, untracked → untouched by the reset) and data (Postgres volume, unaffected) verified intact before/after; the engine container was never restarted so live account connections never dropped. Local = GitHub = VPS at `00e7f7a`.
- **2026-07-20** — **§15.4 done — Sticky Top Navigation & User/Staff Profile Management.** Non-breaking: authentication logic, roles and permissions are unchanged, and **no migration was needed** (every field already existed on `users`). **Backend:** `MeUpdate` and `UserUpdate` gain `email`; new `PasswordChange` schema; `users.email_taken(email, exclude_id)` helper and `update_user(email=…)`. `PATCH /api/auth/me` now also updates the email — rejecting a blank name (`422 "Name cannot be empty."`) and a taken address (`409 "This email address is already in use."`, excluding yourself so re-saving your own email is fine). New **`POST /api/auth/change-password`** verifies the current password with bcrypt (`400 "Current password is incorrect."`), enforces ≥8 chars, is audit-logged, and deliberately **does not** invalidate tokens so the user stays logged in. `PATCH /api/users/{id}` gains the same email-uniqueness + name-required guards. **Frontend:** the top bar is now `position: sticky; top: 0; z-index: 50` with a shadow once scrolled; the user chip became a button opening a dropdown (**My Profile / Change Password / Log out**, click-outside to close) — `UserMenu.tsx`, `ProfileModal.tsx` (editable name + email; read-only role / status / created; updates the cached user so the chip refreshes with no page reload), `ChangePasswordModal.tsx` (current / new / confirm with client-side match + length checks). Staff gains an **Actions** column with a ✏️ per row opening `EditStaffModal.tsx` (name, email, role, active toggle, optional password — blank keeps the current one), plus a sticky header and hover. New `.form-success` style for the "…updated successfully." notifications. **Bug found and fixed during E2E:** the scroll-shadow listener was bound only to `.content`, but the layout grows past the viewport so the **window** is the real scroll container — the handler now watches both (and it's `position: sticky` that actually keeps the bar pinned). **Verified:** 212 pytest pass (9 new: profile name/email update incl. same-email, blank name 422, duplicate email 409, full change-password flow — wrong current 400, success, token still valid, old password rejected + new accepted — min-length 422, staff edit name/email/role, staff duplicate email 409, staff optional-password keep-vs-change, staff blank name 422); `npm run build` clean; **browser E2E** — dropdown opened, profile renamed (success message + chip updated live), password mismatch and wrong-current-password both rejected then changed successfully while staying logged in (old password 401 / new 200 confirmed via API), staff member edited (name + email + role → row updated with no reload) and a duplicate email rejected with the exact spec message, sticky bar verified pinned at `top: 0` with the shadow class applied while the window scrolled; no console errors.
- **2026-07-20** — **§15.5 done — Inbox UX & Performance Upgrade (Meta Business Suite style).** Telegram messaging logic, conversation storage and the contact-stage workflow are untouched; **no migration needed**. **Backend:** `inbox.get_thread()` gained `limit` / `before_id` / `q` — `limit` returns the **newest** N (so a chat opens at the latest message) always serialised oldest→newest, `before_id` pages further back, and `q` searches **within that conversation only**; new `has_older_messages()` drives the "Load older" affordance, and `count_conversations()` + a shared `_conversations_filter()` back the batched list. New **`GET /api/inbox/conversations/{id}/messages`** (`limit`/`before_id`/`q` → `{messages, has_more}`); the thread endpoint now defaults to the latest **12** and returns `has_more`; `GET /api/inbox/conversations` accepts `limit`/`offset` and sets **`X-Total-Count`** (no limit still returns everything, so existing callers are unaffected). `save_peer_as_contact()` accepts full details (name/phone/username/source/stage/consent) and **updates a matched contact instead of duplicating**, raising `DuplicateContact` (409) when an identifier belongs to someone else; the thread's contact payload gained `name`/`telegram_user_id`/`notes`. **Frontend:** the Inbox was rebuilt as a three-pane Meta-style workspace — sticky conversation header + sticky composer with **only the message history scrolling**, latest-12 loading with a "Load older messages" button that **preserves scroll position**, a 20-at-a-time conversation list with "Load more", richer conversation rows (avatar, name, @username, last message, timestamp, stage badge, unread count, connected account, active highlight), a redesigned contact panel (large avatar, Telegram ID, phone, stage, source, consent, account + **Edit contact / Copy username / Copy phone**), a full **Save as contact** modal, and **search-in-conversation** that highlights hits and scrolls to them (plus "Jump to latest"). Responsive per §10/§11: desktop three columns, tablet narrower panes, and on mobile the list opens first → a conversation fills the screen with a **back button**, contact details slide over as a **drawer** with a scrim, no horizontal scrolling; the composer is an auto-growing textarea (capped at 140px) that lifts above the mobile keyboard via `visualViewport`. **Bug found and fixed during E2E:** the conversation list and message history were **not scrolling internally at all** — flex/grid children default to `min-height: auto`, so the thread body grew to its content and pushed the page, defeating the sticky composer; adding `min-height: 0` is what actually gives both panes their own scrollbars. **Verified:** 220 pytest pass (8 new: opens at the newest 12 with `has_more`, paging back with `before_id` until exhausted, short thread reports no older, in-conversation search is partial/case-insensitive and does not leak across chats, conversation batching with `X-Total-Count` and non-overlapping pages, save-contact with full details, save-contact updating an existing match instead of duplicating); `npm run build` clean; **browser E2E** on a 25-conversation seed with a 30-message chat — 20 conversations then "Load more" → 25, chat opened at message 29 with exactly 12 loaded, "Load older" prepended 12 more with **scrollTop 0→727 and the anchor message still in view**, in-chat search found and highlighted "pricing" and scrolled to it, contact edited from the panel and the change appeared in the Contacts module, and at 375×812 the list→chat→back flow plus the slide-over drawer worked with **no horizontal scroll**; composer grew 39→140px and stayed visible. No console errors.
- **2026-07-20** — **§15.6 done — Telegram Account Management & Identity Display Upgrade.** Login, sessions, QR/phone/session-string sign-in, health, spam and logout are all untouched. **Note:** the drafted spec **ends mid-modal** (no sections 3+, no Acceptance Criteria); the implemented scope is the Objective plus sections 1–2 as written, confirmed with the user first. **Backend:** migration **`0017`** adds `accounts.tg_user_id` / `tg_username` / `tg_first_name` — the account's *real* Telegram identity, kept separate from our operator `label`. `accounts.record_identity()` parses the engine's user payload (strips a leading `@`, `+`-prefixes the phone, ignores missing keys) and `mark_logged_in()` now takes that payload, so **all four login paths** (QR, QR-password, phone sign-in, session import) capture it; `GET /accounts/{id}/status` refreshes it too, so an already-logged-in account fills in without re-login. The operator's own label is never overwritten and a manually entered phone is never clobbered. New **`PATCH /api/accounts/{id}`** is the single unified edit: renames (rejecting a blank name with `422 "Account name cannot be empty."`), and manages the proxy — `assign_proxy:false` releases it to the pool, `true` + `proxy_id` binds a specific one (`409` if another account holds it, `404` if unknown), `true` alone auto-assigns a free proxy — then best-effort re-binds the live engine client when the proxy actually changed, and is audit-logged. `AccountOut` gained the three identity fields. **Frontend:** a single **✏️ Edit** per row opens `AccountEditModal.tsx` (Account name · read-only Telegram identity · Assign-proxy checkbox + proxy picker with the free proxies plus the one it already holds), matching the drafted mock-up; the Accounts table's old "Phone" column became a **"Telegram identity"** column showing first name / @username / phone with explicit "not logged in" and "unknown — run Health" states, and the actions moved into a proper Actions column. **Cross-test pollution fixed:** the new suite imports proxies and assigns them, which broke `test_proxy_import_and_auto_assign`'s global "exactly 1 assigned" assertion — rather than loosen that existing check, the §15.6 tests now namespace their labels (`p156-…`) and an autouse fixture hands every proxy they took back to the pool. **Verified:** 231 pytest pass (11 new: identity captured on login incl. `@`-stripping and `+`-prefixing, operator phone preserved, status-check refresh, no identity when the engine reports none, rename, blank-name 422, proxy auto-assign then release-to-pool, specific-proxy selection, 409 on a proxy owned by another account, label+proxy together, manager-only RBAC); migration `0017` up/down on SQLite; `npm run build` clean; **browser E2E** — the list showed the real identity (`Sales One / @sales_one_tg / +8801700000001`) with exactly **one Edit button per row**, the modal rendered all three sections with the identity read-only, renaming + switching proxy 10.9.0.1→10.9.0.3 updated both the account **and** the pool (old one freed, new one bound), and unchecking "Assign proxy" released it with all three proxies back to **free**. No console errors.

---

## 15. Post-v1 Update Phase — Bug Fixes & Enhancements

**Status: DEFINED (not started).** v1 (phases 0–12) is complete and **deployed to the
Hetzner VPS** at commit `93a0f43` (`https://crm.46-225-170-211.nip.io`, nginx-fronted,
CRM in Docker under `/opt/telegram-crm`).

**Process rules for this phase (do not skip):**
- Work lands in the **local repo + GitHub first**. The **VPS is updated only on an
  explicit "deploy" request** — never automatically as part of a fix.
- Each item follows the safe loop: **reproduce → add a failing test → minimal, localized
  fix → full verification (`pytest` all green + migration up/down if the schema changed +
  `npm run build` + a browser E2E for UI-facing changes) → tick the tracker below → append
  a dated note to §14 → one atomic commit per item** (so any change can be reverted alone).
- **Architecture invariants still hold:** only the Telegram Engine Service owns Telethon
  clients; the API/worker call it via `engine_client`. Media is streamed **from Telegram
  on demand, never persisted on the VPS**. Backups are **Admin-only**.

### 15.0 Progress tracker (tick as completed)

- [ ] **15.1 Inbox & messaging overhaul**
  - [x] 15.1.a **Fix (critical):** sending a message fails everywhere with `engine error 500: Internal Server Error` — fixed 2026-07-16 (numeric-id target coerced to int; see §14)
  - [x] 15.1.b Inbound media rendering — image / video / gif / sticker / file / voice, shown **from Telegram** (not stored on the VPS) — done 2026-07-16 (see §14)
  - [x] 15.1.c Outbound media & voice — send image / video / file / voice from the chat, uploaded **directly to Telegram** (not stored on the VPS) — done 2026-07-16 (see §14)
  - [x] 15.1.d Contact panel (right) shows the peer's details; chat header shows the peer name; **"Save as contact"** for a message from an unsaved peer — done 2026-07-16 (see §14)
  - [x] 15.1.e Multi-account inbox selector — **all / one / many** accounts, with a **searchable account picker** — done 2026-07-16 (see §14)
  - [x] 15.1.f Show **which account** owns each conversation (list + chat) — done 2026-07-16 (see §14)
  - [x] 15.1.g **Conversation search** box, scoped to the selected account(s) — done 2026-07-16 (see §14)
  - [x] 15.1.h **Conversation retention** — history stays in the CRM even if the peer deletes it on Telegram (text kept; media, not stored, may become unavailable) — done 2026-07-16 (see §14)
  - [x] 15.1.i **Conversation actions** — **Archive** and **Delete** a conversation from the inbox — done 2026-07-16 (see §14)
  - [x] 15.1.j **Archive folder** — an Archive view listing all archived chats (open / unarchive) — done 2026-07-16 (see §14)
- [x] **15.2 Backup & Restore center* In setting option so make a setting option inthe option list* — done 2026-07-16: lives under a new **Settings** nav option (Admin only), per this note
  - [x] 15.2.a Full backup (Postgres data + Telethon `sessions/` + settings) with **selectable scope**, default = everything — done 2026-07-16 (see §14)
  - [x] 15.2.b **Restore** from a backup — done 2026-07-16 (see §14)
  - [x] 15.2.c **Downloadable** backups; keep the **last 5** — done 2026-07-16 (see §14)
  - [x] 15.2.d **Delete** a backup from the server — done 2026-07-16 (see §14)
  - [x] 15.2.e **Auto-backup on/off** + schedule (daily, or every N days) — done 2026-07-16 (see §14)
  - [x] 15.2.f **Load a backup file** — upload a previously downloaded archive back onto the server, then Restore it — done 2026-07-16 (see §14)
- [x] **15.3 Contacts Module UX & Management Upgrade** — done 2026-07-20 (see §14); non-breaking (stage system, Pipeline/Inbox/Campaigns/Analytics/Sender untouched)
  - [x] 15.3.a Modern contact list — avatar (initials), Name + @username + Phone shown together, rounded badges, sticky header, hover, responsive
  - [x] 15.3.b **Edit Contact** — name / phone / username / source / stage / consent / **notes**; open via ✏️ or double-click; saves without a page refresh
  - [x] 15.3.c **Duplicate prevention** — phone & username unique (409 "Phone number already exists." / "Username already exists." on create + edit); **Import now UPDATES** an existing match instead of duplicating
  - [x] 15.3.d **Import summary** (imported / updated / no-consent / invalid / errors) + **Export** CSV & Excel (all / filtered / selected)
  - [x] 15.3.e Better search (name / username / phone / source, debounced) + filters (stage / lead type / resolution / consent / source) that combine
  - [x] 15.3.f **Bulk actions** — change stage, mark/remove consent, resolve/unresolve, export, delete (confirm); select current page / all matching / clear
  - [x] 15.3.g Pagination (rows 10/25/50/100, "Showing X–Y of N"), empty state, loading skeletons
- [x] **15.4 Sticky Top Navigation & User/Staff Profile Management** — done 2026-07-20 (see §14); non-breaking (auth logic, roles & permissions unchanged)
  - [x] 15.4.a **Sticky top nav** — `position: sticky; top: 0; z-index: 50` + a subtle shadow once scrolled (watches both the window and the `.content` pane); sidebar untouched
  - [x] 15.4.b **User profile menu** — the logged-in user chip is now a button opening a dropdown: My Profile / Change Password / Log out
  - [x] 15.4.c **My Profile** — edit full name + email; role / account status / created date read-only; email unique, name required; saves without logout or refresh
  - [x] 15.4.d **Change Password** — current / new / confirm; current password verified **server-side**; min 8 chars; confirm must match; user is **not** logged out
  - [x] 15.4.e **Staff edit** — Actions column + ✏️ per row opening a modal: full name, email, role, active status, optional password (blank = keep current)
  - [x] 15.4.f **Account security** — duplicate emails rejected with "This email address is already in use." on both profile and staff edit; passwords always bcrypt-hashed and never displayed
  - [x] 15.4.g Staff table: Actions column, sticky header, hover, better spacing; success notifications on profile / password / staff updates
- [x] **15.5 Inbox UX & Performance Upgrade (Meta Business Suite style)** — done 2026-07-20 (see §14); Telegram messaging logic, conversation storage and stage workflow unchanged
  - [x] 15.5.a Three-pane layout (list / conversation / contact) with **independent scrolling**; sticky conversation header + sticky composer — only the message history scrolls
  - [x] 15.5.b **Smart message loading** — opens at the newest message, loads the latest **12**, "Load older messages" pages back **preserving scroll position**
  - [x] 15.5.c **Batched conversation list** — latest **20** + "Load more conversations"; existing search/filters/folders unchanged
  - [x] 15.5.d **Edit Contact** from the panel (reuses the §15.3 modal — phone/username stay unique) and syncs instantly with the Contacts module
  - [x] 15.5.e **Save Contact** with full details (name/phone/username/source/stage/consent) — an existing match is **updated**, never duplicated
  - [x] 15.5.f **Search in conversation** — scoped server-side to that chat, partial + case-insensitive, hits highlighted and scrolled into view (with "Jump to latest")
  - [x] 15.5.g Richer conversation rows (avatar, name, username, last message, timestamp, stage badge, unread count, connected account, active highlight) and contact panel (avatar, Telegram ID, phone, stage, source, consent, account + Copy username / Copy phone)
  - [x] 15.5.h **Fully responsive** — desktop 3-column, tablet narrower panes, mobile list→full-screen chat with a back button and a slide-over contact drawer, no horizontal scrolling
  - [x] 15.5.i **Responsive composer** — auto-grows with the message (capped), always visible, and lifts above the mobile keyboard via `visualViewport`
- [x] **15.6 Telegram Account Management & Identity Display Upgrade** — done 2026-07-20 (see §14); login/session/QR/phone/health/spam/logout untouched
  - [x] 15.6.a **One unified Edit button** per account — a single modal covering account name, Telegram identity and proxy; no separate name/proxy/enable/disable buttons
  - [x] 15.6.b **Edit Account modal** — Account Name, read-only **Telegram Identity** (first name / @username / phone / ID), Proxy **Assign yes-no** + proxy selection, Cancel / Save Changes
  - [x] 15.6.c **Real Telegram identity captured** — migration `0017` adds `tg_user_id` / `tg_username` / `tg_first_name`, populated from the engine on every login path and refreshed on a status check; our own `label` is never overwritten and an operator-entered phone is never clobbered
  - [x] 15.6.d **Identity shown in the Accounts list** — a "Telegram identity" column (name / @username / phone) with clear "not logged in" and "unknown — run Health" states
  - [x] 15.6.e **Proxy management from the same modal** — enable (auto-assign a free proxy), pick a specific proxy, or disable (released back to the pool); a proxy already held by another account is rejected, and a live client is re-bound when its proxy changes

> **Note on §15.6:** the drafted spec ends mid-modal (no sections 3+ and no Acceptance
> Criteria). Implemented scope = the Objective plus sections 1–2 as written, confirmed with
> the user before building.

### 15.1 Inbox & messaging overhaul

Builds on the existing inbox (models `conversations`/`messages` — migration `0005`,
`engine/listener.py`, `inbox_consumer.py`, `services/inbox.py`, `api/inbox.py`,
`frontend/src/pages/Inbox.tsx`, `useInboxSocket`). The `messages` table already has
`type` (text/image/voice/link) and `media_ref` fields to extend.

**15.1.a — Sending is broken (fix first, highest priority).**
Right now sending a reply from the Inbox — and sending from any account, from anywhere
(Contacts message, Sender, Campaigns) — fails with **`engine error 500: Internal Server
Error`**. This blocks the product's core function, so it is the first fix.
- *Reproduce:* open a conversation → type a reply → **Send** → observe the 500. Also try
  Contacts → message an account. Capture the engine traceback (`docker compose logs engine`)
  and the backend traceback.
- *Fix:* trace the outbound path (`api/inbox` → `services/inbox` → `engine_client.send_message`
  → engine `send_dm`) and repair the actual error; add a regression test that drives a send
  with the engine mocked to assert a 200 + recorded outgoing message, and (where possible)
  a live smoke send on the VPS after deploy.
- *Done when:* a reply sends successfully from the Inbox and lands in the thread; sending
  from Contacts/Sender/Campaigns works; no 500s.

**15.1.b — Show inbound media (image / video / gif / sticker / voice / file).**
Incoming non-text messages currently can't be seen. Render them inline in the thread.
- Media must be **served from Telegram on demand — not saved on the VPS.** Approach: the
  engine downloads the media bytes for a given message on request and **streams** them back
  through a backend endpoint (e.g. `GET /api/inbox/messages/{id}/media`) that proxies the
  engine; nothing is written to persistent VPS storage (transient in-memory/temp only, then
  discarded; a short-lived cache is acceptable but not required).
- The listener (`engine/listener.py`) must detect the media type on incoming messages and
  record `type` + a Telegram file reference in `media_ref` (not a local path).
- Rendering: images/gifs as `<img>`, video as `<video>`, voice as an inline audio player
  (waveform/duration is a nice-to-have), files as a download chip with name/size. Animated
  stickers (`.tgs`/Lottie) may render as a **static preview** initially — full animation is
  optional.
- *Done when:* an inbound photo, video, gif, sticker, voice note, and document each display
  (or are playable/downloadable) in the conversation, fetched from Telegram with **no media
  file written to the VPS**.

**15.1.c — Send media & voice from the chat.**
The composer must send image / video / file / **voice message**, like normal Telegram.
- Outbound media is uploaded **directly to Telegram** via the engine (`send_file` already
  exists) and **not kept on the VPS** (a transient temp during upload is discarded).
- Voice: record in the browser (MediaRecorder → opus/ogg) and send as a Telegram **voice
  note**; files/images/videos via an attach button.
- Sent media appears in the same thread (and, like text, is consistent with campaign/manual
  history).
- *Done when:* staff can attach & send an image, a video, a document, and record & send a
  voice message from a conversation, all delivered through Telegram with nothing persisted
  on the VPS.

**15.1.d — Contact panel + save-from-inbox.**
The right-hand panel currently says "No linked contact" even when a real peer is messaging.
- Right panel shows the **peer's details** (name, @username, phone, Telegram user id, and
  the linked CRM contact's stage/tags/history if one exists).
- The **chat header shows the peer's name** (falling back to @username, then id).
- When a message arrives from a peer with **no CRM contact**, offer **"Save as contact"**
  that creates a `Contact` from the peer (pre-filled name/username/phone; note the consent
  model — an inbound peer initiated contact, so saving with `consent=true` is defensible and
  should be recorded with `source="inbox"`).
- *Done when:* the right panel shows peer/contact details, the header shows the name, and an
  unsaved inbound peer can be saved as a contact in one click and immediately links to the
  conversation.

**15.1.e / 15.1.f / 15.1.g — Multi-account inbox controls.**
The inbox needs first-class multi-account handling:
- **Account selector** to choose whose inbox to show: **all accounts**, a **single account**,
  or **several accounts**, driven by a **searchable account picker** (search accounts by
  label to select them). Backend: `GET /api/inbox/conversations?account_ids=…`.
- Each conversation shows **which account** it belongs to (account label in the list item,
  and in the chat header / right panel — "conversation via <account>").
- A separate **conversation search** box filters conversations (by peer name / last-message)
  **within the selected account(s)**. Backend: a `q` query param.
- *Done when:* the operator can filter the inbox to all / one / many accounts via a
  searchable picker, see which account each conversation uses, and search conversations
  within the current selection.

**15.1.h — Conversation retention (never lose history).**
All conversations & messages are **kept in the CRM as the system of record** — they **remain
even if the peer deletes them on Telegram** (the CRM holds its own copy). Because media is
not stored on the VPS (§15.1.b), media the peer later deletes on Telegram may become
unavailable; in that case keep the message record and any text and show a **"media no longer
available"** placeholder. A Telegram-side deletion must **never** cascade into removing CRM
records.
- *Done when:* a message still appears in the CRM thread after being deleted on Telegram
  (text preserved; unavailable media shown as a placeholder).

**15.1.i — Conversation actions (Archive / Delete).**
Each conversation gets an **action menu** in the inbox, with at least **Archive** and
**Delete**:
- **Archive** — flag the conversation archived (an `archived` flag, kept independent of the
  pipeline stage/status; new migration `0011`), removing it from the main inbox list **without
  losing history**.
- **Delete** — an operator-initiated removal of the conversation (and its messages) from the
  CRM; **destructive → requires a confirm step.** This is distinct from a *peer* deleting on
  Telegram, which never removes CRM data (see 15.1.h).
- *Done when:* an operator can archive or delete a conversation from the inbox, delete asks
  for confirmation, and neither affects the peer's Telegram.

**15.1.j — Archive folder.**
The inbox has an **Archive** view/folder listing **all archived conversations**; from it a
chat can be opened and **unarchived** (returned to the main inbox). The main inbox list shows
only non-archived chats by default.
- *Done when:* archiving moves a chat out of the main list into the Archive folder, archived
  chats are viewable there, and they can be unarchived back to the main inbox.

### 15.2 Backup & Restore center

Extends the Phase-12 headless backup (`scripts/backup.sh`, `backup-loop.sh`, the `backup`
compose service, retention) into an **Admin-only, UI-driven** backup manager. A **full**
backup must capture everything needed to reconstitute the system:
- **Postgres data** (all tables — settings, accounts, contacts, conversations, messages,
  campaigns, bots, referrals, …) via `pg_dump`.
- **Telethon `sessions/`** files — *required* so restored accounts stay logged in (a DB-only
  backup would lose the live account sessions).
- **Settings / config** (the tunable app settings; the raw `.env` secrets are excluded from
  downloads by default for safety — call this out in the UI).
- Media is **not** included (it is never stored on the VPS).

**15.2.a — Backup with selectable scope.**
- A backup screen (Settings or a dedicated **Backup** page) with **checkboxes to choose
  scope** (Database, Sessions/Accounts, Settings). **Default = everything.**
- Creating a backup produces a single archive on the server (e.g. `/backups/…​.tar.gz`).
- *Done when:* an Admin can trigger a backup of the selected components and it appears in the
  backup list.

**15.2.b — Restore.**
- Restore from a stored (or uploaded) backup archive. Must warn that restore is **disruptive**
  (services quiesced during DB/session restore) and require confirmation.
- *Done when:* restoring a backup returns the system to that backup's state (data + logged-in
  accounts) after a controlled restart.

**15.2.c / 15.2.d — Manage backups.**
- List backups with timestamp/size/scope; **download** an archive (Admin-only, over HTTPS —
  archives contain sessions = full account access, so downloads must be authenticated);
  **keep the last 5** (older ones auto-pruned by count); **delete** a backup from the server.
- *Done when:* the last 5 backups are listed, each can be downloaded and deleted, and a 6th
  backup prunes the oldest.

**15.2.f — Load a backup file (upload).**
Restore from an archive you downloaded earlier: upload the `.tar.gz`, it is **validated
as a real CRM backup** (its `manifest.json` must be present and sane) before being
accepted, then it appears in the list and is restored with the normal Restore action.
Uploaded archives are stored under a fresh name so they sort as newest and are **never
pruned out from under you**, while the original creation time is kept and shown.
Admin-only; size-capped by `BACKUP_MAX_UPLOAD_MB`.
- *Done when:* a downloaded backup file can be uploaded and then restored, and a file
  that isn't a valid CRM archive is rejected.

**15.2.e — Auto-backup schedule.**
- **On/off** toggle for automatic backups, plus a schedule: **daily** or **every N days**
  (configurable). Replaces the fixed `BACKUP_INTERVAL_SECONDS` with a UI-editable setting;
  the `backup` service / a Celery beat task honors it.
- *Done when:* auto-backup can be turned on/off and set to run daily or every N days, and the
  schedule is respected.

> **Security note for §15.2:** backup archives include Telethon session files and full DB
> data — treat them as top-secret. All backup/restore/download/delete endpoints are
> **Admin-only**, served over HTTPS, and never exposed publicly.


### 15.3 — Contacts Module UX & Management Upgrade (Modern CRM Experience)

## Objective

Upgrade the existing **Contacts** page to provide a modern CRM experience while **keeping all existing functionality exactly as it is**.

This phase is only a UI/UX enhancement and adds missing contact management features.

---

# Critical Requirements

- Do NOT remove any existing feature.
- Do NOT change any existing business logic.
- Do NOT change existing APIs unless absolutely required.
- Do NOT modify other CRM modules.
- Everything outside the Contacts page must continue working exactly as before.

---

# 1. Keep Existing Stage System (VERY IMPORTANT)

The current Contact Stage system is already connected with:

- Pipeline
- Inbox
- Campaigns
- Analytics
- Sender
- CRM Automation

Therefore it MUST remain exactly as it is.

Keep these exact values:

- new
- contacted
- replied
- joined
- customer
- opted_out

Requirements:

- Do NOT rename stages.
- Do NOT add new stages.
- Do NOT remove stages.
- Do NOT change database values.
- Do NOT change API values.
- Do NOT change existing automation.
- Keep the current "Set Stage" dropdown functionality exactly the same.
- The Edit Contact modal must use this exact stage list.

Only improve:

- dropdown styling
- spacing
- badges
- colors
- icons

Functionality must remain 100% backward compatible.

---

# 2. Modern Contact List

Redesign the contacts table to look like a modern CRM (HubSpot / GoHighLevel style).

Each row should display:

- Checkbox
- Avatar (generated from initials)
- Contact Name
- Telegram Username
- Phone Number
- Lead Type
- Stage Badge
- Resolution Badge
- Consent
- Source
- Created Date
- Quick Actions

Display format:

If Name exists:

Ahmed Khan
@ahmedkhan
+923001234567

If Name is empty:

@ahmedkhan
+923001234567

If Username is empty:

Ahmed Khan
+923001234567

If only phone exists:

+923001234567

Always display username if available.

Never hide the username.

---

# 3. Edit Contact

Add a complete Edit Contact feature.

Open by:

- Edit button
- Double-click row

Modal fields:

- Name
- Phone
- Username
- Source
- Stage
- Consent

Future-ready field:

- Notes

Save changes without refreshing the page.

---

# 4. Duplicate Prevention

A contact must only exist once.

Phone numbers must be unique.

Usernames must be unique.

Validation:

If phone already exists:

"Phone number already exists."

If username already exists:

"Username already exists."

During Import:

If a contact already exists:

- Update the existing record
- Never create duplicate contacts

---

# 5. Import Improvements

Keep existing Import feature.

Enhance it with:

- Import progress
- Better validation
- Better error handling
- Import summary

Example:

Imported: 150

Updated: 20

Skipped: 5

Duplicates Updated: 18

Errors: 2

Duplicate contacts should UPDATE existing records instead of creating new ones.

---

# 6. Export Contacts

Add Export button beside Import.

Support:

- CSV
- Excel (.xlsx)

Export options:

- Export All Contacts
- Export Selected Contacts
- Export Filtered Contacts

Export fields:

- Name
- Phone
- Username
- Source
- Stage
- Resolution
- Consent
- Created Date

---

# 7. Better Bulk Selection

Improve multi-selection.

Add:

- Select All Contacts
- Select Current Page
- Clear Selection

Display:

"15 Contacts Selected"

instead of

"15 selected"

---

# 8. Bulk Actions

Create a Bulk Actions dropdown.

Actions:

- Change Stage
- Delete
- Export Selected
- Mark Consent
- Remove Consent
- Resolve Contacts
- Unresolve Contacts

Delete should ask confirmation.

Example:

Delete 25 selected contacts?

Cancel

Delete

---

# 9. Better Search

Keep existing search.

Improve it to search:

- Name
- Username
- Phone
- Source

Search should update instantly.

---

# 10. Better Filters

Keep current Stage filter.

Add filters for:

- Lead Type
- Resolution Status
- Consent
- Source

Filters should work together.

---

# 11. Quick Actions

Replace large action buttons with modern icon buttons.

Actions:

- Message
- Resolve
- Edit
- Delete

Show tooltips on hover.

---

# 12. Table Improvements

Improve the table without changing functionality.

Add:

- Sticky table header
- Better spacing
- Better typography
- Hover effect
- Rounded badges
- Responsive layout
- Cleaner buttons
- Better row spacing

No changes outside this page.

---

# 13. Empty State

If there are no contacts, show a modern empty state.

Example:

No contacts found.

Import contacts

or

Add your first contact.

---

# 14. Loading States

Show loading skeletons while:

- Loading contacts
- Searching
- Importing
- Exporting
- Updating

Avoid blank screens.

---

# 15. Pagination Improvements

Keep existing pagination.

Add:

Rows per page:

- 10
- 25
- 50
- 100

Show:

Showing 26–50 of 1,248 contacts

---

# 16. Performance

Optimize for large datasets.

Support:

- 10,000+ contacts
- Fast search
- Fast pagination
- Fast bulk actions

---

# 17. Acceptance Criteria

This phase is complete when:

✅ All existing features continue working exactly the same.

✅ No existing business logic is changed.

✅ Contact Stage system remains exactly the same.

✅ Pipeline continues working.

✅ Inbox continues working.

✅ Campaigns continue working.

✅ Analytics continues working.

✅ Sender continues working.

✅ Edit Contact works.

✅ Import works.

✅ Export works.

✅ Duplicate contacts cannot be created.

✅ Phone numbers are unique.

✅ Usernames are unique.

✅ Duplicate imports update existing contacts instead of creating new ones.

✅ Contact rows display:

- Name
- Username
- Phone

at the same time.

✅ Select All works.

✅ Select Current Page works.

✅ Bulk Actions work.

✅ Delete confirmation works.

✅ Modern CRM UI.

✅ Responsive design.

✅ No regressions anywhere else in the CRM.

This phase is a non-breaking enhancement to the existing Contacts module. It only modernizes the UI and adds missing contact management features while preserving 100% compatibility with the existing CRM.


### 15.4 — Sticky Top Navigation & User/Staff Profile Management

## Objective

Enhance the CRM's top navigation and Staff module by adding profile management features while keeping all existing functionality unchanged.

This phase only improves the user experience and adds account management capabilities.

---

# Critical Requirements

- Do NOT remove any existing functionality.
- Do NOT change authentication logic.
- Do NOT modify user roles or permissions.
- Do NOT affect any other CRM modules.
- Keep the current design language consistent.
- All existing login and staff management functionality must continue working exactly as before.

---

# 1. Sticky Top Navigation Bar

The top navigation bar containing:

- Telegram Marketing CRM
- Theme Toggle
- Logged-in User
- Logout Button

must always remain visible.

Requirements:

- Sticky at the top of the page.
- Remains visible while scrolling.
- Same width as the content area.
- Maintain existing styling.
- Add a subtle shadow or border when scrolling.
- Smooth scrolling behavior.
- High z-index so it stays above all page content.
- Must work on all CRM pages.

No changes to the sidebar.

---

# 2. Logged-in User Profile Menu

The logged-in user section in the top-right corner should become clickable.

Clicking it should open a dropdown or modal with:

- My Profile
- Change Password
- Logout

---

# 3. My Profile

Create a Profile modal/page for the currently logged-in user.

Editable fields:

- Full Name
- Email Address

Read-only fields:

- Role
- Account Status
- Created Date

Validation:

- Email must be unique.
- Name cannot be empty.

Save without requiring logout.

---

# 4. Change Password

Add a secure Change Password form.

Fields:

- Current Password
- New Password
- Confirm New Password

Validation:

- Current password must be correct.
- New password minimum 8 characters.
- Confirm password must match.

Show success message after update.

Do NOT log the user out after changing the password.

---

# 5. Staff Management Improvements

Keep the current Staff page.

Add an Edit action for every staff member.

Each staff row should include:

- Edit
- Reset Password (optional)
- Activate / Deactivate (future-ready)

Do NOT remove any existing columns.

---

# 6. Edit Staff Member

Clicking Edit opens a modal.

Editable fields:

- Full Name
- Email
- Password (optional)
- Role (only if current user has permission)

If password is left empty:

- Keep the existing password.

If a new password is entered:

- Update the password.

Validation:

- Email must be unique.
- Name is required.
- Password minimum 8 characters if provided.

---

# 7. Staff Table Improvements

Keep the current table.

Add:

- Action column
- Edit icon
- Better spacing
- Hover effect
- Sticky header
- Responsive layout

No other functionality should change.

---

# 8. Account Security

Prevent duplicate email addresses.

Validation:

If email already exists:

"This email address is already in use."

Passwords must always be securely hashed.

Never display existing passwords.

---

# 9. User Experience

After updating:

- Profile
- Staff Member
- Password

Show a success notification.

Example:

Profile updated successfully.

Password changed successfully.

Staff member updated successfully.

No page refresh should be required.

---

# 10. Acceptance Criteria

This phase is complete when:

✅ The top navigation bar is sticky on every page.

✅ The CRM title remains visible while scrolling.

✅ Logged-in users can edit their own profile.

✅ Logged-in users can change their password.

✅ Staff members can be edited.

✅ Staff email can be updated.

✅ Staff full name can be updated.

✅ Staff password can be changed.

✅ Email addresses remain unique.

✅ Existing authentication continues working.

✅ Existing permissions continue working.

✅ No existing functionality is removed.

✅ No regressions are introduced.

This phase is a non-breaking enhancement that adds profile management and improves the CRM navigation while maintaining full backward compatibility with the existing authentication, permissions, and staff management system.

### 15.5 — Inbox UX & Performance Upgrade (Meta Business Suite Style)

## Objective

Modernize the Inbox to provide a Meta Business Suite–style experience while keeping all existing Telegram messaging logic, APIs, workflows, and CRM integrations unchanged.

---

## Critical Requirements

- Do NOT change Telegram messaging logic.
- Do NOT change conversation storage.
- Do NOT change contact stage workflow.
- Do NOT modify Contacts, Pipeline, Sender, Campaigns, or other modules.
- Only improve the Inbox UI, contact management, responsiveness, and performance.

---

## 1. Modern Inbox Layout

Redesign the Inbox similar to Meta Business Suite.

Layout:

- Left: Conversation List
- Center: Conversation
- Right: Contact Information

Keep all existing functionality.

---

## 2. Sticky Conversation

Inside the conversation panel:

### Sticky Header

Always visible:

- Contact Name
- Stage
- Archive
- Delete

### Sticky Composer

Always visible:

- Attachment Button
- Message Input
- Send Button

Only the message history should scroll.

---

## 3. Smart Message Loading

When opening a conversation:

- Automatically open at the newest message.
- Scroll to the bottom by default.
- Load only the latest **12 messages** initially.
- Show a **Load Older Messages** button at the top.
- Each click loads the next batch of older messages.
- Preserve scroll position while loading.

This keeps conversations loading fast.

---

## 4. Optimized Conversation List

The left conversation list should have its own scrollbar.

Performance rules:

- Load only the latest **20 conversations** initially.
- Show **Load More Conversations** at the bottom.
- Clicking loads the next batch.
- Preserve scroll position.
- Existing search and filters continue working.

This prevents heavy page loads.

---

## 5. Contact Management

Add **Edit Contact** inside the Contact panel.

Editable fields:

- Name
- Phone
- Username
- Source
- Stage
- Consent

Validation:

- Phone must remain unique.
- Username must remain unique.

Updates should instantly sync with the Contacts module.

---

## 6. Save Contact Improvements

Keep the existing Save Contact feature.

Allow entering:

- Name
- Phone
- Username
- Source
- Stage
- Consent

If the contact already exists:

- Update the existing contact.
- Never create duplicate contacts.

---

## 7. Search Inside Conversation

Inside the Contact panel add:

**Search in Conversation**

Search only within the currently opened conversation.

Support:

- Message text
- Partial words
- Future-ready date search

Matching messages should be highlighted and automatically scrolled into view.

---

## 8. Conversation List Improvements

Each conversation should display:

- Avatar
- Contact Name
- Username (if available)
- Last Message
- Timestamp
- Stage Badge
- Unread Count
- Connected Account

Highlight the active conversation.

---

## 9. Contact Panel Improvements

Improve the design only.

Display:

- Avatar
- Name
- Username
- Telegram ID
- Phone
- Stage
- Source
- Consent
- Connected Account

Quick actions:

- Edit Contact
- Copy Username
- Copy Phone

---

## 10. Fully Responsive Inbox

The entire Inbox must be fully responsive on desktop, tablet, and mobile.

### Desktop

- Three-column layout.
- Sticky header.
- Sticky composer.
- Independent scrolling for conversations and message history.

### Tablet

- Automatically adjust panel widths.
- Maintain sticky behavior.

### Mobile

Modern messaging experience similar to:

- Meta Business Suite
- WhatsApp
- Telegram
- Messenger

Requirements:

- Conversation list opens first.
- Opening a conversation shows the chat full-screen.
- Contact details open as a separate slide-over panel or drawer.
- Back button returns to the conversation list.
- No horizontal scrolling.
- Touch-friendly spacing and buttons.

---

## 11. Responsive Message Composer

The bottom message composer must adapt to every screen size.

Requirements:

- Width automatically adjusts with screen size.
- Input grows naturally for longer messages.
- Composer always remains visible.

### Mobile Keyboard Behavior

When the mobile keyboard appears:

- The message composer should automatically move above the keyboard.
- The input field must never be hidden behind the keyboard.
- The latest messages should remain visible while typing.
- The conversation should resize smoothly without layout jumps.

The typing experience should feel like modern messaging apps such as WhatsApp, Telegram, Messenger, and Meta Business Suite.

---

## 12. Performance

Optimize for large inboxes.

Requirements:

- Fast conversation switching.
- Latest messages load first.
- Older messages load on demand.
- Conversation list loads in batches.
- Smooth scrolling.
- No unnecessary page refreshes.

---

## Acceptance Criteria

✅ Existing Inbox functionality remains unchanged.

✅ Conversation opens at the newest message.

✅ Latest 12 messages load initially.

✅ Older messages load only on demand.

✅ Conversation list loads only 20 conversations initially.

✅ More conversations load when requested.

✅ Sticky conversation header.

✅ Sticky responsive message composer.

✅ Message composer remains visible while scrolling.

✅ Message composer moves above the mobile keyboard.

✅ Entire Inbox is fully responsive on desktop, tablet, and mobile.

✅ Contact editing works.

✅ Save Contact supports full contact details.

✅ Contact updates sync across the CRM.

✅ Search inside the current conversation works.

✅ No duplicate contacts.

✅ Modern Meta Business Suite–style interface.

✅ No regressions introduced.


### 15.6 — Telegram Account Management & Identity Display Upgrade

## Objective

Improve the existing Accounts section by adding a single unified Edit option for each Telegram account and displaying the account's actual Telegram identity more clearly.

All existing Telegram login, session, proxy, health, spam, logout, and account functionality must remain unchanged.

---

## Critical Requirements

- Do NOT change the existing Telegram login/session system.
- Do NOT change QR login, phone login, or session login.
- Do NOT change account health or spam logic.
- Do NOT change logout or remove functionality.
- Do NOT affect Inbox, Campaigns, Sender, or other CRM modules.
- Keep all existing functionality working exactly as before.

---

# 1. One Unified Edit Button

Add one single **Edit** button for each account.

All account editing functionality must be inside this one Edit option.

The Edit modal must include:

- Account Name / Label
- Telegram Identity Information
- Proxy Enable / Disable
- Proxy Selection

There should NOT be separate edit buttons for:

- Name
- Proxy
- Enable proxy
- Disable proxy

Everything must be managed from the same Edit modal.

---

# 2. Edit Account Modal

Example:

```text
Edit Account

Account Name
[ Sales1                  ]

Telegram Identity
@username
+880XXXXXXXXXX

Proxy

yes or no :  Assign proxy


[Cancel] [Save Changes]