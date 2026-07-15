"""Contacts: CSV/Excel import, dedupe, CRUD, resolution, and messaging."""

import csv
import io
from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.account import Account
from app.db.models.contact import Contact
from app.db.models.proxy import Proxy
from app.services import engine_client

CSV_TEMPLATE = (
    "name,phone,username,source,consent\n"
    "Ahmed Khan,+923001234567,,offline_store,true\n"
    "Sara Ali,,@sara_ali,online_store,true\n"
    ",+14155550123,,online_store,true\n"
    ",,@no_name_user,online_store,true\n"
)

_TRUE_VALUES = {"true", "1", "yes", "y", "t"}


class NoResolverAccount(Exception):
    """No logged-in account is available to resolve/message a contact."""


# ------------------------------------------------------------- normalising ---


def normalize_phone(value) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    cleaned = "".join(ch for ch in s if ch.isdigit() or ch == "+")
    return cleaned or None


def normalize_username(value) -> str | None:
    if value is None:
        return None
    s = str(value).strip().lstrip("@").lower()
    return s or None


def parse_bool(value) -> bool:
    return str(value).strip().lower() in _TRUE_VALUES if value is not None else False


# ---------------------------------------------------------------- parsing ----


def _clean_headers(headers: list) -> list[str]:
    return [str(h).strip().lower() if h is not None else "" for h in headers]


def parse_csv(data: bytes) -> list[dict]:
    text = data.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for raw in reader:
        rows.append({(k or "").strip().lower(): v for k, v in raw.items()})
    return rows


def parse_xlsx(data: bytes) -> list[dict]:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    try:
        headers = _clean_headers(list(next(rows_iter)))
    except StopIteration:
        return []
    rows = []
    for values in rows_iter:
        if values is None or all(v is None for v in values):
            continue
        rows.append({headers[i]: values[i] if i < len(values) else None for i in range(len(headers))})
    wb.close()
    return rows


def parse_upload(filename: str, data: bytes) -> list[dict]:
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xlsm")):
        return parse_xlsx(data)
    return parse_csv(data)


# ----------------------------------------------------------------- import ----


async def import_contacts(db: AsyncSession, rows: list[dict]) -> dict:
    existing = await db.execute(
        select(Contact.phone, Contact.username)
    )
    existing_phones: set[str] = set()
    existing_usernames: set[str] = set()
    for phone, username in existing.all():
        if phone:
            existing_phones.add(phone)
        if username:
            existing_usernames.add(username)

    seen_phones: set[str] = set()
    seen_usernames: set[str] = set()
    imported = skipped = rejected = invalid = 0

    for row in rows:
        name = (str(row.get("name")).strip() if row.get("name") else "") or None
        phone = normalize_phone(row.get("phone"))
        username = normalize_username(row.get("username"))
        source = (str(row.get("source")).strip() if row.get("source") else "") or None
        consent = parse_bool(row.get("consent"))

        if not phone and not username:
            invalid += 1
            continue
        if not consent:
            rejected += 1
            continue

        is_dup = (phone and (phone in existing_phones or phone in seen_phones)) or (
            username and (username in existing_usernames or username in seen_usernames)
        )
        if is_dup:
            skipped += 1
            continue

        if phone:
            seen_phones.add(phone)
        if username:
            seen_usernames.add(username)

        db.add(
            Contact(
                name=name,
                lead_type="phone" if phone else "username",
                phone=phone,
                username=username,
                source=source,
                consent=True,
                tags=[],
                utm={},
            )
        )
        imported += 1

    await db.commit()
    total = await db.scalar(select(func.count()).select_from(Contact))
    return {
        "imported": imported,
        "skipped_duplicates": skipped,
        "rejected_no_consent": rejected,
        "invalid": invalid,
        "total": int(total or 0),
    }


# ------------------------------------------------------------------ CRUD -----


async def get_by_id(db: AsyncSession, contact_id: int) -> Contact | None:
    return await db.get(Contact, contact_id)


async def list_contacts(
    db: AsyncSession,
    *,
    assigned_agent_id: int | None = None,
    stage: str | None = None,
    source: str | None = None,
    resolution: str | None = None,
    q: str | None = None,
) -> list[Contact]:
    stmt = select(Contact)
    if assigned_agent_id is not None:
        stmt = stmt.where(Contact.assigned_agent_id == assigned_agent_id)
    if stage:
        stmt = stmt.where(Contact.stage == stage)
    if source:
        stmt = stmt.where(Contact.source == source)
    if resolution:
        stmt = stmt.where(Contact.resolution_status == resolution)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(
                Contact.name.ilike(like),
                Contact.username.ilike(like),
                Contact.phone.ilike(like),
            )
        )
    stmt = stmt.order_by(Contact.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def create_contact(
    db: AsyncSession,
    *,
    name: str | None,
    phone: str | None,
    username: str | None,
    source: str | None,
    consent: bool,
    tags: list | None,
) -> Contact:
    phone = normalize_phone(phone)
    username = normalize_username(username)
    contact = Contact(
        name=name,
        lead_type="phone" if phone else "username",
        phone=phone,
        username=username,
        source=source,
        consent=consent,
        tags=tags or [],
        utm={},
    )
    db.add(contact)
    await db.commit()
    await db.refresh(contact)
    return contact


async def update_contact(db: AsyncSession, contact: Contact, **fields) -> Contact:
    for key, value in fields.items():
        if value is not None:
            setattr(contact, key, value)
    await db.commit()
    await db.refresh(contact)
    return contact


async def delete_contact(db: AsyncSession, contact: Contact) -> None:
    await db.delete(contact)
    await db.commit()


# ------------------------------------------------- resolution & messaging ----


async def _account_proxy(db: AsyncSession, account: Account) -> Proxy | None:
    if account.proxy_id is None:
        return None
    return await db.get(Proxy, account.proxy_id)


async def pick_resolver_account(db: AsyncSession, contact: Contact) -> Account | None:
    if contact.assigned_account_id:
        acc = await db.get(Account, contact.assigned_account_id)
        if acc and acc.session_ref and acc.status in ("active", "warming"):
            return acc
    result = await db.execute(
        select(Account)
        .where(
            Account.session_ref.isnot(None),
            Account.status.in_(["active", "warming"]),
        )
        .order_by(Account.id)
        .limit(1)
    )
    return result.scalar_one_or_none()


async def resolve_contact(db: AsyncSession, contact: Contact) -> Contact:
    account = await pick_resolver_account(db, contact)
    if account is None:
        raise NoResolverAccount()
    proxy = await _account_proxy(db, account)

    if contact.lead_type == "username" and contact.username:
        data = await engine_client.resolve_username(account, proxy, contact.username)
    elif contact.lead_type == "phone" and contact.phone:
        data = await engine_client.resolve_phone(account, proxy, contact.phone)
    else:
        contact.resolution_status = "failed"
        await db.commit()
        await db.refresh(contact)
        return contact

    contact.telegram_user_id = data.get("user_id")
    contact.resolution_status = data.get("status", "failed")
    await db.commit()
    await db.refresh(contact)
    return contact


def message_target(contact: Contact) -> str | None:
    if contact.telegram_user_id:
        return str(contact.telegram_user_id)
    if contact.username:
        return f"@{contact.username}"
    if contact.phone:
        return contact.phone
    return None


async def message_contact(
    db: AsyncSession, contact: Contact, account: Account, text: str
) -> Contact:
    proxy = await _account_proxy(db, account)
    target = message_target(contact)
    if target is None:
        raise ValueError("contact has no reachable identifier")
    result = await engine_client.send_message(account, proxy, target, text)
    if not result.get("sent", False):
        raise engine_client.EngineUnavailable(f"send failed: {result.get('error')}")
    contact.last_contacted_at = datetime.now(timezone.utc)
    if contact.stage == "new":
        contact.stage = "contacted"
    await db.commit()
    await db.refresh(contact)
    return contact
