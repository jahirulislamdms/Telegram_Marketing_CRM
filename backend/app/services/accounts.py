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


async def mark_logged_in(db: AsyncSession, account: Account) -> Account:
    account.session_ref = str(account.id)
    account.status = "active"
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
