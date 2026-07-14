"""Account manager endpoints (Admin/Manager).

CRUD plus login flows (QR / phone / session-string import) that delegate all
Telegram work to the engine via the engine client.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_manager
from app.config import settings
from app.db.models.proxy import Proxy
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.account import (
    AccountCreate,
    AccountOut,
    AccountStatus,
    AccountStatusUpdate,
    AppealResult,
    BanCheckResult,
    LoginResultResponse,
    PasswordRequest,
    PhoneSendCodeRequest,
    PhoneSendCodeResponse,
    PhoneSignInRequest,
    QrLoginResponse,
    QrStatusResponse,
    SessionStringImport,
    SpamCheckResult,
)
from app.services import accounts as account_service
from app.services import audit
from app.services import engine_client
from app.services import proxies as proxy_service

router = APIRouter(prefix="/accounts", tags=["accounts"])


async def _get_account_or_404(db: AsyncSession, account_id: int):
    account = await account_service.get_by_id(db, account_id)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return account


async def _account_proxy(db: AsyncSession, account) -> Proxy | None:
    if account.proxy_id is None:
        return None
    return await db.get(Proxy, account.proxy_id)


def _engine_error(exc: engine_client.EngineUnavailable) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"Telegram engine unavailable: {exc}",
    )


# ---------------------------------------------------------------- CRUD --------


@router.get("", response_model=list[AccountOut])
async def list_accounts(
    _: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> list:
    return await account_service.list_accounts(db)


@router.post("", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
async def create_account(
    payload: AccountCreate,
    user: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> AccountOut:
    account = await account_service.create_account(
        db,
        label=payload.label,
        phone=payload.phone,
        api_id=payload.api_id,
        api_hash=payload.api_hash,
    )
    if payload.assign_proxy:
        await proxy_service.assign_free_proxy(db, account)
        await db.refresh(account)
    await audit.record_event(
        db,
        type="account.create",
        actor_type="user",
        actor_id=user.id,
        entity_ref=f"account:{account.id}",
        meta={"label": account.label},
    )
    return account


@router.get("/{account_id}", response_model=AccountOut)
async def get_account(
    account_id: int,
    _: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> AccountOut:
    return await _get_account_or_404(db, account_id)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    account_id: int,
    user: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> None:
    account = await _get_account_or_404(db, account_id)
    # Best-effort logout on the engine; ignore if it is unreachable.
    try:
        await engine_client.logout(account_id)
    except engine_client.EngineUnavailable:
        pass
    await proxy_service.release_proxy(db, account)
    await audit.record_event(
        db,
        type="account.delete",
        actor_type="user",
        actor_id=user.id,
        entity_ref=f"account:{account_id}",
    )
    await db.delete(account)
    await db.commit()


# -------------------------------------------------------------- status --------


@router.get("/{account_id}/status", response_model=AccountStatus)
async def account_status(
    account_id: int,
    _: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> AccountStatus:
    account = await _get_account_or_404(db, account_id)
    try:
        data = await engine_client.get_status(account_id)
    except engine_client.EngineUnavailable as exc:
        return AccountStatus(
            id=account.id,
            label=account.label,
            status=account.status,
            engine_reachable=False,
            detail=str(exc),
        )
    return AccountStatus(
        id=account.id,
        label=account.label,
        status=account.status,
        connected=data.get("connected", False),
        authorized=data.get("authorized", False),
        telegram_user=data.get("user"),
        engine_reachable=True,
    )


@router.post("/reconnect")
async def reconnect_all(
    _: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Ask the engine to (re)start clients for every account with a session."""
    accounts = await account_service.list_accounts(db)
    started, failed = 0, 0
    for account in accounts:
        if not account.session_ref:
            continue
        proxy = await _account_proxy(db, account)
        try:
            await engine_client.start_client(account, proxy)
            started += 1
        except engine_client.EngineUnavailable:
            failed += 1
    return {"started": started, "failed": failed}


# --------------------------------------------------------------- login --------


@router.post("/{account_id}/login/qr", response_model=QrLoginResponse)
async def login_qr_start(
    account_id: int,
    _: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> QrLoginResponse:
    account = await _get_account_or_404(db, account_id)
    proxy = await _account_proxy(db, account)
    try:
        data = await engine_client.qr_start(account, proxy)
    except engine_client.EngineUnavailable as exc:
        raise _engine_error(exc)
    return QrLoginResponse(url=data["url"], expires_at=data.get("expires_at"))


@router.get("/{account_id}/login/qr", response_model=QrStatusResponse)
async def login_qr_status(
    account_id: int,
    _: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> QrStatusResponse:
    account = await _get_account_or_404(db, account_id)
    try:
        data = await engine_client.qr_status(account_id)
    except engine_client.EngineUnavailable as exc:
        raise _engine_error(exc)
    if data.get("status") == "authorized":
        await account_service.mark_logged_in(db, account)
    return QrStatusResponse(**data)


@router.post("/{account_id}/login/qr/password", response_model=LoginResultResponse)
async def login_qr_password(
    account_id: int,
    payload: PasswordRequest,
    _: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> LoginResultResponse:
    account = await _get_account_or_404(db, account_id)
    try:
        data = await engine_client.qr_password(account_id, payload.password)
    except engine_client.EngineUnavailable as exc:
        raise _engine_error(exc)
    if data.get("status") == "authorized":
        await account_service.mark_logged_in(db, account)
    return LoginResultResponse(**data)


@router.post(
    "/{account_id}/login/phone/send-code", response_model=PhoneSendCodeResponse
)
async def login_phone_send_code(
    account_id: int,
    payload: PhoneSendCodeRequest,
    _: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> PhoneSendCodeResponse:
    account = await _get_account_or_404(db, account_id)
    proxy = await _account_proxy(db, account)
    try:
        data = await engine_client.phone_send_code(account, proxy, payload.phone)
    except engine_client.EngineUnavailable as exc:
        raise _engine_error(exc)
    return PhoneSendCodeResponse(phone_code_hash=data["phone_code_hash"])


@router.post("/{account_id}/login/phone/sign-in", response_model=LoginResultResponse)
async def login_phone_sign_in(
    account_id: int,
    payload: PhoneSignInRequest,
    _: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> LoginResultResponse:
    account = await _get_account_or_404(db, account_id)
    try:
        data = await engine_client.phone_sign_in(
            account_id,
            payload.phone,
            payload.code,
            payload.phone_code_hash,
            payload.password,
        )
    except engine_client.EngineUnavailable as exc:
        raise _engine_error(exc)
    if data.get("status") == "authorized":
        await account_service.mark_logged_in(db, account)
    return LoginResultResponse(**data)


@router.post("/{account_id}/login/session", response_model=LoginResultResponse)
async def login_session_string(
    account_id: int,
    payload: SessionStringImport,
    _: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> LoginResultResponse:
    account = await _get_account_or_404(db, account_id)
    proxy = await _account_proxy(db, account)
    try:
        data = await engine_client.import_session(account, proxy, payload.session_string)
    except engine_client.EngineUnavailable as exc:
        raise _engine_error(exc)
    if data.get("status") == "authorized":
        await account_service.mark_logged_in(db, account)
    return LoginResultResponse(**data)


@router.post("/{account_id}/logout", response_model=AccountOut)
async def logout_account(
    account_id: int,
    user: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> AccountOut:
    account = await _get_account_or_404(db, account_id)
    try:
        await engine_client.logout(account_id)
    except engine_client.EngineUnavailable as exc:
        raise _engine_error(exc)
    await account_service.mark_logged_out(db, account)
    await audit.record_event(
        db,
        type="account.logout",
        actor_type="user",
        actor_id=user.id,
        entity_ref=f"account:{account_id}",
    )
    return account


# ------------------------------------------------------- status & health -----


@router.patch("/{account_id}/status", response_model=AccountOut)
async def override_status(
    account_id: int,
    payload: AccountStatusUpdate,
    user: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> AccountOut:
    """Manually override an account's status."""
    account = await _get_account_or_404(db, account_id)
    previous = account.status
    updated = await account_service.set_status(db, account, payload.status)
    await audit.record_event(
        db,
        type="account.status_override",
        actor_type="user",
        actor_id=user.id,
        entity_ref=f"account:{account_id}",
        meta={"from": previous, "to": payload.status},
    )
    return updated


def _require_logged_in(account) -> None:
    if not account.session_ref:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account is not logged in",
        )


@router.post("/{account_id}/health/spam-check", response_model=SpamCheckResult)
async def spam_check(
    account_id: int,
    user: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> SpamCheckResult:
    account = await _get_account_or_404(db, account_id)
    _require_logged_in(account)
    proxy = await _account_proxy(db, account)
    try:
        data = await engine_client.spam_check(account, proxy)
    except engine_client.EngineUnavailable as exc:
        raise _engine_error(exc)

    spam_state = data.get("spam_state", "unknown")
    await account_service.set_spam_state(db, account, spam_state)

    quarantined = False
    if spam_state in ("limited", "banned") and settings.auto_quarantine_on_warning:
        new_status = "banned" if spam_state == "banned" else "quarantined"
        await account_service.set_status(db, account, new_status)
        quarantined = True
        await audit.record_event(
            db,
            type="account.quarantine",
            actor_type="system",
            entity_ref=f"account:{account_id}",
            meta={"reason": f"spam_state={spam_state}", "status": new_status},
        )

    await audit.record_event(
        db,
        type="account.spam_check",
        actor_type="user",
        actor_id=user.id,
        entity_ref=f"account:{account_id}",
        meta={"spam_state": spam_state},
    )
    return SpamCheckResult(
        spam_state=spam_state,
        reply=data.get("reply"),
        quarantined=quarantined,
        detail=data.get("detail"),
    )


@router.post("/{account_id}/health/ban-check", response_model=BanCheckResult)
async def ban_check(
    account_id: int,
    user: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> BanCheckResult:
    account = await _get_account_or_404(db, account_id)
    _require_logged_in(account)
    proxy = await _account_proxy(db, account)
    try:
        data = await engine_client.ban_check(account, proxy)
    except engine_client.EngineUnavailable as exc:
        raise _engine_error(exc)

    state = data.get("state", "error")
    if state == "banned":
        await account_service.set_status(db, account, "banned")
        await audit.record_event(
            db,
            type="account.quarantine",
            actor_type="system",
            entity_ref=f"account:{account_id}",
            meta={"reason": "ban_check", "status": "banned"},
        )
    elif state == "unauthorized":
        await account_service.mark_logged_out(db, account)

    await db.refresh(account)
    return BanCheckResult(
        state=state,
        telegram_user=data.get("user"),
        status=account.status,
        detail=data.get("detail"),
    )


@router.post("/{account_id}/health/unspam", response_model=AppealResult)
async def request_unspam(
    account_id: int,
    user: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> AppealResult:
    account = await _get_account_or_404(db, account_id)
    _require_logged_in(account)
    proxy = await _account_proxy(db, account)
    try:
        data = await engine_client.request_unspam(account, proxy)
    except engine_client.EngineUnavailable as exc:
        raise _engine_error(exc)
    await audit.record_event(
        db,
        type="account.unspam_request",
        actor_type="user",
        actor_id=user.id,
        entity_ref=f"account:{account_id}",
    )
    return AppealResult(**data)


@router.post("/{account_id}/health/unfreeze", response_model=AppealResult)
async def request_unfreeze(
    account_id: int,
    user: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> AppealResult:
    account = await _get_account_or_404(db, account_id)
    _require_logged_in(account)
    proxy = await _account_proxy(db, account)
    try:
        data = await engine_client.request_unfreeze(account, proxy)
    except engine_client.EngineUnavailable as exc:
        raise _engine_error(exc)
    await audit.record_event(
        db,
        type="account.unfreeze_request",
        actor_type="user",
        actor_id=user.id,
        entity_ref=f"account:{account_id}",
    )
    return AppealResult(**data)
