# Deployment & Operations Guide

Self-hosted deployment of the **Telegram Marketing CRM** with Docker Compose,
automatic HTTPS via Caddy, and nightly PostgreSQL backups. Two supported hosts:
an **Ubuntu VPS** (recommended for internet-facing use) and **Windows** (Docker
Desktop). Both use the same compose files.

> Internal company use only. Target **consented contacts** and **company-owned**
> channels/groups. Opt-outs are honored automatically and permanently.

---

## 1. What you get

- One command brings up: PostgreSQL, Redis, the FastAPI backend, the Celery
  worker + beat scheduler, the Telegram engine, the React frontend, Caddy (TLS),
  and (in production) a `backup` service.
- **HTTPS** is issued and renewed automatically by Caddy once a domain points at
  the server.
- **Rate limiting** (per-IP, tighter on login), **security headers**, and a
  **startup secrets guard** that refuses to boot production with default secrets.
- **Nightly `pg_dump`** backups with rotation, written to `./backups`.

---

## 2. Prerequisites

- A server with **Docker** and the **Docker Compose plugin** (`docker compose`, v2).
- For HTTPS: a **domain name** with an A/AAAA record pointing at the server's
  public IP, and inbound **ports 80 and 443** open.
- Telegram **API ID / API HASH** from <https://my.telegram.org> (needed before you
  log in any Telegram accounts, not for first boot).

---

## 3. Ubuntu VPS install

### 3.1 Install Docker

```bash
# Docker's official convenience script
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"   # log out/in so the group takes effect
docker --version && docker compose version
```

### 3.2 Get the code and configure

```bash
git clone https://github.com/jahirulislamdms/Telegram_Marketing_CRM.git
cd Telegram_Marketing_CRM
cp .env.example .env
```

Edit `.env` and set, at minimum:

| Variable | Set to |
|---|---|
| `ENVIRONMENT` | `production` |
| `DEBUG` | `false` |
| `SECRET_KEY` | a strong random value — `openssl rand -hex 32` |
| `BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD` | your real admin login |
| `POSTGRES_PASSWORD` | a strong DB password |
| `CORS_ORIGINS` | your site URL, e.g. `https://crm.example.com` |
| `CADDY_SITE_ADDRESS` | your domain, e.g. `crm.example.com` |
| `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` | from my.telegram.org |

Generate a secret without leaving the repo:

```bash
docker compose run --rm backend python -m app.cli generate-secret
```

Verify there are no insecure defaults left (the backend also runs this on boot):

```bash
docker compose run --rm backend python -m app.cli prod-check
```

### 3.3 Point DNS

Create an **A record** (and **AAAA** if you have IPv6) for `crm.example.com`
pointing at the server IP. Confirm it resolves before starting Caddy, or ACME
will fail to issue a certificate:

```bash
dig +short crm.example.com
```

### 3.4 Launch (production)

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Caddy obtains a certificate automatically. Then:

- App: `https://crm.example.com`
- Health: `https://crm.example.com/health`
- Readiness (DB + Redis): `https://crm.example.com/health/ready`

Log in with the bootstrap admin credentials from `.env` and change the password.

### 3.5 Firewall (recommended)

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

Postgres (5432) and Redis (6379) are **not** published to the host in production
(the compose prod overrides clear their `ports`), so they are only reachable on
the internal Docker network.

---

## 4. Windows install (Docker Desktop)

1. Install **Docker Desktop** and enable the WSL 2 backend.
2. In PowerShell:
   ```powershell
   git clone https://github.com/jahirulislamdms/Telegram_Marketing_CRM.git
   cd Telegram_Marketing_CRM
   Copy-Item .env.example .env
   ```
3. Edit `.env` as in §3.2. For a **local** run leave `CADDY_SITE_ADDRESS=:80`
   (no TLS) and reach the app at `http://localhost`. For a public domain, set it
   to your domain and forward ports 80/443 to the machine.
4. Start:
   - Local/dev: `docker compose up --build`
   - Production: `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`

Same URLs as above (`http://localhost` for the local case).

---

## 5. Backups & restore

The production `backup` service runs `scripts/backup-loop.sh`, which calls
`scripts/backup.sh` immediately and then every `BACKUP_INTERVAL_SECONDS`
(default daily). Dumps are gzipped into `./backups` and rotated after
`BACKUP_RETENTION_DAYS` (default 14).

Check backups:

```bash
ls -lh backups/
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs backup
```

Run a backup on demand:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm backup sh /scripts/backup.sh
```

Restore a dump (**stop the app first** so nothing writes during restore):

```bash
# Example file name; use one from ./backups
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm \
  -v "$PWD/backups:/backups" backup \
  sh /scripts/restore.sh /backups/telegram_crm-20260715-030000.sql.gz
```

> Keep off-server copies too — sync `./backups` to object storage or another host
> on a schedule. A backup you can't restore from elsewhere is not a backup.

---

## 6. Operations

| Task | Command |
|---|---|
| View logs | `docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f backend` |
| Restart a service | `docker compose ... restart backend` |
| Update to latest code | `git pull && docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build` |
| Run DB migrations manually | `docker compose ... run --rm backend alembic upgrade head` |
| Create another admin | `docker compose ... run --rm backend python -m app.cli create-admin --email a@b.com --password '...'` |
| Stop everything | `docker compose -f docker-compose.yml -f docker-compose.prod.yml down` |

Migrations run automatically on backend startup (`alembic upgrade head`).

---

## 7. Security checklist (before going live)

- [ ] `ENVIRONMENT=production` and `DEBUG=false` in `.env`.
- [ ] `SECRET_KEY` is a fresh 32-byte random value (not the default).
- [ ] Bootstrap admin password changed from `admin12345`; logged in and rotated.
- [ ] `POSTGRES_PASSWORD` is strong; DB/Redis ports not published (prod default).
- [ ] `CORS_ORIGINS` set to your exact site URL (not `*`).
- [ ] `docker compose ... run --rm backend python -m app.cli prod-check` passes.
- [ ] HTTPS works (`https://` shows a valid certificate); HSTS header present.
- [ ] Rate limiting enabled (`RATE_LIMIT_ENABLED=true`); `429` returned when
      hammering `/api/auth/login`.
- [ ] Firewall allows only 22/80/443.
- [ ] Backups are being written to `./backups` and copied off-server.
- [ ] `sessions/` volume is persisted (Telethon logins survive restarts).

---

## 8. Troubleshooting

- **Caddy can't get a certificate** — DNS isn't pointing at the server yet, or
  ports 80/443 are blocked. Check `docker compose ... logs caddy`.
- **Backend exits immediately in production** — the secrets guard rejected an
  insecure default. Run `... run --rm backend python -m app.cli prod-check` and
  fix what it lists.
- **`/health/ready` returns 503** — Postgres is unreachable; check the `postgres`
  service and credentials. (Redis being down is reported but does not fail
  readiness — the API still serves, but Celery-driven pacing/broadcasts pause.)
- **Too many `429`s** — raise `RATE_LIMIT_PER_MINUTE` / `RATE_LIMIT_LOGIN_PER_MINUTE`
  in `.env` and restart, or set `RATE_LIMIT_ENABLED=false` to disable entirely.

---

Developed by **Jahirul Islam** — <https://jahirulislam.info/>
