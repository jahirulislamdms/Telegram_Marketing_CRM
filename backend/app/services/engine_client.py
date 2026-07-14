"""HTTP client for the Telegram Engine Service's private API.

The backend never opens a Telethon client itself — it calls the engine over the
internal Docker network. All Telegram side effects happen in the engine process.
"""

from typing import Any

import httpx

from app.config import settings
from app.db.models.account import Account
from app.db.models.proxy import Proxy


class EngineUnavailable(RuntimeError):
    """Raised when the engine cannot be reached or returns an error."""


def proxy_payload(proxy: Proxy | None) -> dict[str, Any] | None:
    if proxy is None:
        return None
    return {
        "type": proxy.type,
        "host": proxy.host,
        "port": proxy.port,
        "username": proxy.username,
        "password": proxy.password,
    }


def credentials_payload(account: Account, proxy: Proxy | None) -> dict[str, Any]:
    from app.services.accounts import effective_api_credentials

    api_id, api_hash = effective_api_credentials(account)
    return {
        "api_id": api_id,
        "api_hash": api_hash,
        "proxy": proxy_payload(proxy),
    }


async def _request(method: str, path: str, json: dict | None = None) -> Any:
    url = f"{settings.engine_url}{path}"
    try:
        async with httpx.AsyncClient(timeout=settings.engine_timeout_seconds) as client:
            resp = await client.request(method, url, json=json)
    except httpx.HTTPError as exc:
        raise EngineUnavailable(f"engine request failed: {exc}") from exc

    if resp.status_code >= 500:
        raise EngineUnavailable(f"engine error {resp.status_code}: {resp.text}")
    if resp.status_code >= 400:
        detail = resp.json().get("detail") if resp.headers.get(
            "content-type", ""
        ).startswith("application/json") else resp.text
        raise EngineUnavailable(f"engine rejected request ({resp.status_code}): {detail}")
    if resp.status_code == 204 or not resp.content:
        return None
    return resp.json()


async def health() -> dict:
    return await _request("GET", "/health")


async def start_client(account: Account, proxy: Proxy | None) -> dict:
    return await _request(
        "POST", f"/clients/{account.id}/start", json=credentials_payload(account, proxy)
    )


async def get_status(account_id: int) -> dict:
    return await _request("GET", f"/clients/{account_id}/status")


async def logout(account_id: int) -> dict:
    return await _request("POST", f"/clients/{account_id}/logout")


async def import_session(
    account: Account, proxy: Proxy | None, session_string: str
) -> dict:
    body = credentials_payload(account, proxy)
    body["session_string"] = session_string
    return await _request("POST", f"/clients/{account.id}/login/session", json=body)


async def qr_start(account: Account, proxy: Proxy | None) -> dict:
    return await _request(
        "POST", f"/clients/{account.id}/login/qr", json=credentials_payload(account, proxy)
    )


async def qr_status(account_id: int) -> dict:
    return await _request("GET", f"/clients/{account_id}/login/qr")


async def qr_password(account_id: int, password: str) -> dict:
    return await _request(
        "POST", f"/clients/{account_id}/login/qr/password", json={"password": password}
    )


async def phone_send_code(account: Account, proxy: Proxy | None, phone: str) -> dict:
    body = credentials_payload(account, proxy)
    body["phone"] = phone
    return await _request(
        "POST", f"/clients/{account.id}/login/phone/send-code", json=body
    )


async def phone_sign_in(
    account_id: int,
    phone: str,
    code: str,
    phone_code_hash: str,
    password: str | None,
) -> dict:
    return await _request(
        "POST",
        f"/clients/{account_id}/login/phone/sign-in",
        json={
            "phone": phone,
            "code": code,
            "phone_code_hash": phone_code_hash,
            "password": password,
        },
    )


# ---- Health (Phase 3) ----


async def spam_check(account: Account, proxy: Proxy | None) -> dict:
    return await _request(
        "POST",
        f"/clients/{account.id}/health/spam-check",
        json=credentials_payload(account, proxy),
    )


async def ban_check(account: Account, proxy: Proxy | None) -> dict:
    return await _request(
        "POST",
        f"/clients/{account.id}/health/ban-check",
        json=credentials_payload(account, proxy),
    )


async def request_unspam(account: Account, proxy: Proxy | None) -> dict:
    return await _request(
        "POST",
        f"/clients/{account.id}/health/unspam",
        json=credentials_payload(account, proxy),
    )


async def request_unfreeze(account: Account, proxy: Proxy | None) -> dict:
    return await _request(
        "POST",
        f"/clients/{account.id}/health/unfreeze",
        json=credentials_payload(account, proxy),
    )


# ---- Warmup actions (Phase 4) ----


async def warmup_join(account: Account, proxy: Proxy | None, link: str) -> dict:
    body = credentials_payload(account, proxy)
    body["link"] = link
    return await _request("POST", f"/clients/{account.id}/warmup/join", json=body)


async def warmup_send(
    account: Account, proxy: Proxy | None, target: str, text: str
) -> dict:
    body = credentials_payload(account, proxy)
    body["target"] = target
    body["text"] = text
    return await _request("POST", f"/clients/{account.id}/warmup/send", json=body)
