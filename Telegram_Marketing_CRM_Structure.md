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
  - [ ] 15.1.d Contact panel (right) shows the peer's details; chat header shows the peer name; **"Save as contact"** for a message from an unsaved peer
  - [ ] 15.1.e Multi-account inbox selector — **all / one / many** accounts, with a **searchable account picker**
  - [ ] 15.1.f Show **which account** owns each conversation (list + chat)
  - [ ] 15.1.g **Conversation search** box, scoped to the selected account(s)
  - [ ] 15.1.h **Conversation retention** — history stays in the CRM even if the peer deletes it on Telegram (text kept; media, not stored, may become unavailable)
  - [ ] 15.1.i **Conversation actions** — **Archive** and **Delete** a conversation from the inbox
  - [ ] 15.1.j **Archive folder** — an Archive view listing all archived chats (open / unarchive)
- [ ] **15.2 Backup & Restore center* another seperate options in the option list*
  - [ ] 15.2.a Full backup (Postgres data + Telethon `sessions/` + settings) with **selectable scope**, default = everything
  - [ ] 15.2.b **Restore** from a backup
  - [ ] 15.2.c **Downloadable** backups; keep the **last 5**
  - [ ] 15.2.d **Delete** a backup from the server
  - [ ] 15.2.e **Auto-backup on/off** + schedule (daily, or every N days)

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

**15.2.e — Auto-backup schedule.**
- **On/off** toggle for automatic backups, plus a schedule: **daily** or **every N days**
  (configurable). Replaces the fixed `BACKUP_INTERVAL_SECONDS` with a UI-editable setting;
  the `backup` service / a Celery beat task honors it.
- *Done when:* auto-backup can be turned on/off and set to run daily or every N days, and the
  schedule is respected.

> **Security note for §15.2:** backup archives include Telethon session files and full DB
> data — treat them as top-secret. All backup/restore/download/delete endpoints are
> **Admin-only**, served over HTTPS, and never exposed publicly.
