"""Proxy pool: parsing, bulk import, and assignment."""

from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.account import Account
from app.db.models.proxy import Proxy

_SCHEME_TO_TYPE = {
    "socks5": "socks5",
    "socks5h": "socks5",
    "socks": "socks5",
    "http": "http",
    "https": "http",
    "mtproxy": "mtproxy",
    "mtproto": "mtproxy",
}


class ProxyParseError(ValueError):
    pass


def parse_proxy_line(line: str) -> dict:
    """Parse a single proxy string into its components.

    Supported formats:
      - ``host:port``
      - ``host:port:user:pass``
      - ``scheme://[user:pass@]host:port`` (scheme: socks5/http/mtproxy/...)

    Returns a dict: ``{raw, type, host, port, username, password}``.
    Raises :class:`ProxyParseError` on malformed input.
    """
    raw = line.strip()
    if not raw:
        raise ProxyParseError("empty line")

    if "://" in raw:
        parsed = urlparse(raw)
        scheme = (parsed.scheme or "").lower()
        proxy_type = _SCHEME_TO_TYPE.get(scheme)
        if proxy_type is None:
            raise ProxyParseError(f"unsupported scheme: {scheme}")
        if not parsed.hostname or not parsed.port:
            raise ProxyParseError("missing host or port")
        return {
            "raw": raw,
            "type": proxy_type,
            "host": parsed.hostname,
            "port": parsed.port,
            "username": parsed.username or None,
            "password": parsed.password or None,
        }

    parts = raw.split(":")
    if len(parts) == 2:
        host, port = parts
        username = password = None
    elif len(parts) == 4:
        host, port, username, password = parts
    else:
        raise ProxyParseError("expected host:port or host:port:user:pass")

    if not host:
        raise ProxyParseError("missing host")
    try:
        port_int = int(port)
    except ValueError:
        raise ProxyParseError(f"invalid port: {port}")
    if not (0 < port_int < 65536):
        raise ProxyParseError(f"port out of range: {port_int}")

    return {
        "raw": raw,
        "type": "socks5",
        "host": host,
        "port": port_int,
        "username": username or None,
        "password": password or None,
    }


async def list_proxies(db: AsyncSession) -> list[Proxy]:
    result = await db.execute(select(Proxy).order_by(Proxy.created_at.desc()))
    return list(result.scalars().all())


async def _exists(db: AsyncSession, host: str, port: int) -> bool:
    result = await db.execute(
        select(Proxy.id).where(Proxy.host == host, Proxy.port == port)
    )
    return result.first() is not None


async def import_proxies(db: AsyncSession, raw_text: str) -> dict:
    """Bulk-import proxies from pasted text (one per line). Dedupes on host:port."""
    imported = 0
    skipped = 0
    invalid: list[str] = []
    seen_in_batch: set[tuple[str, int]] = set()

    for line in raw_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            parsed = parse_proxy_line(stripped)
        except ProxyParseError:
            invalid.append(stripped)
            continue
        key = (parsed["host"], parsed["port"])
        if key in seen_in_batch or await _exists(db, parsed["host"], parsed["port"]):
            skipped += 1
            continue
        seen_in_batch.add(key)
        db.add(Proxy(**parsed, health="unknown", is_active=True))
        imported += 1

    await db.commit()

    total = len(await list_proxies(db))
    return {
        "imported": imported,
        "skipped_duplicates": skipped,
        "invalid": invalid,
        "total_in_pool": total,
    }


async def assign_free_proxy(db: AsyncSession, account: Account) -> Proxy | None:
    """Assign a free, healthy proxy to the account (one proxy per account)."""
    if account.proxy_id is not None:
        return await db.get(Proxy, account.proxy_id)

    result = await db.execute(
        select(Proxy)
        .where(
            Proxy.is_active.is_(True),
            Proxy.assigned_account_id.is_(None),
            Proxy.health != "dead",
        )
        .order_by(Proxy.id)
        .limit(1)
    )
    proxy = result.scalar_one_or_none()
    if proxy is None:
        return None

    proxy.assigned_account_id = account.id
    account.proxy_id = proxy.id
    await db.commit()
    await db.refresh(proxy)
    return proxy


async def release_proxy(db: AsyncSession, account: Account) -> None:
    if account.proxy_id is None:
        return
    proxy = await db.get(Proxy, account.proxy_id)
    if proxy is not None:
        proxy.assigned_account_id = None
    account.proxy_id = None
    await db.commit()
