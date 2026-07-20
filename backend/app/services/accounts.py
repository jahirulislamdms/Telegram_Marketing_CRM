"""Account persistence and helpers."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models.account import Account


async def get_by_id(db: AsyncSession, account_id: int) -> Account | None:
    return await db.get(Account, account_id)


async def list_accounts(db: AsyncSession) -> list[Account]:
    result = await db.execute(select(Account).order_by(Account.created_at.desc()))
    return list(result.scalars().all())


async def create_account(
    db: AsyncSession,
    *,
    label: str,
    phone: str | None,
    api_id: str | None,
    api_hash: str | None,
) -> Account:
    account = Account(
        label=label,
        phone=phone,
        api_id=api_id,
        api_hash=api_hash,
        status="logged_out",
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return account


async def set_status(db: AsyncSession, account: Account, status: str) -> Account:
    account.status = status
    await db.commit()
    await db.refresh(account)
    return account


async def set_spam_state(db: AsyncSession, account: Account, spam_state: str) -> Account:
    account.spam_state = spam_state
    await db.commit()
    await db.refresh(account)
    return account


async def quarantine(db: AsyncSession, account: Account) -> Account:
    """Auto-quarantine hook: pull the account from rotation."""
    account.status = "quarantined"
    await db.commit()
    await db.refresh(account)
    return account


def _identity_fields(user: dict | None) -> dict:
    """Pull the Telegram identity out of the engine's user payload (§15.6).

    Telethon exposes ``id`` / ``username`` / ``first_name`` / ``phone``; any of
    them may be missing, so each is applied only when present.
    """
    if not isinstance(user, dict):
        return {}
    fields: dict = {}
    if user.get("id") is not None:
        try:
            fields["tg_user_id"] = int(user["id"])
        except (TypeError, ValueError):
            pass
    username = user.get("username")
    if username:
        fields["tg_username"] = str(username).lstrip("@")
    first_name = user.get("first_name")
    if first_name:
        fields["tg_first_name"] = str(first_name)
    phone = user.get("phone")
    if phone:
        p = str(phone)
        fields["phone"] = p if p.startswith("+") else f"+{p}"
    return fields


async def record_identity(
    db: AsyncSession, account: Account, user: dict | None, *, commit: bool = True
) -> Account:
    """Persist the account's real Telegram identity, if the engine reported one.

    The operator-chosen ``label`` is never overwritten; only the phone is filled
    in when Telegram knows it and we don't.
    """
    fields = _identity_fields(user)
    if not fields:
        return account
    for key, value in fields.items():
        # Don't clobber a phone the operator typed in.
        if key == "phone" and account.phone:
            continue
        setattr(account, key, value)
    if commit:
        await db.commit()
        await db.refresh(account)
    return account


async def mark_logged_in(
    db: AsyncSession, account: Account, telegram_user: dict | None = None
) -> Account:
    account.session_ref = str(account.id)
    account.status = "active"
    # Capture who this account actually is on Telegram (§15.6).
    await record_identity(db, account, telegram_user, commit=False)
    await db.commit()
    await db.refresh(account)
    return account


async def update_account(
    db: AsyncSession, account: Account, *, label: str | None = None
) -> Account:
    """Unified account edit (§15.6). Proxy binding is handled by the API layer
    because it also has to release/assign from the shared pool."""
    if label is not None:
        account.label = label
    await db.commit()
    await db.refresh(account)
    return account


async def mark_logged_out(db: AsyncSession, account: Account) -> Account:
    account.session_ref = None
    account.status = "logged_out"
    await db.commit()
    await db.refresh(account)
    return account


def effective_api_credentials(account: Account) -> tuple[str, str]:
    """Return (api_id, api_hash) for the account, falling back to shared creds."""
    api_id = account.api_id or settings.telegram_api_id
    api_hash = account.api_hash or settings.telegram_api_hash
    return api_id, api_hash
