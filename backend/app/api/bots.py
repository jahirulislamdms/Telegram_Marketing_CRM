"""Multi-bot console endpoints (Admin/Manager)."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_manager
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.bot import (
    BotConversationOut,
    BotCreate,
    BotDetail,
    BotMessageOut,
    BotOut,
    BotThreadOut,
    BroadcastRequest,
    PostRequest,
    ReplyRequest,
    SendRequest,
    SimulateBotIncoming,
    SubscriberOut,
)
from app.services import audit
from app.services import bots as bot_service
from app.services import engine_client

router = APIRouter(prefix="/bots", tags=["bots"])


async def _get_bot_or_404(db: AsyncSession, bot_id: int):
    bot = await bot_service.get_bot(db, bot_id)
    if bot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot not found")
    return bot


async def _get_conv_or_404(db: AsyncSession, conversation_id: int):
    from app.db.models.bot import BotConversation

    conv = await db.get(BotConversation, conversation_id)
    if conv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return conv


def _engine_error(exc) -> HTTPException:
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Engine unavailable: {exc}")


@router.get("", response_model=list[BotOut])
async def list_bots(_: User = Depends(require_manager), db: AsyncSession = Depends(get_db)) -> list:
    return await bot_service.list_bots(db)


@router.post("", response_model=BotOut, status_code=status.HTTP_201_CREATED)
async def add_bot(
    payload: BotCreate, user: User = Depends(require_manager), db: AsyncSession = Depends(get_db)
) -> BotOut:
    bot = await bot_service.create_bot(db, payload.token)
    await audit.record_event(
        db, type="bot.add", actor_type="user", actor_id=user.id, entity_ref=f"bot:{bot.id}"
    )
    return bot


@router.get("/{bot_id}", response_model=BotDetail)
async def get_bot(bot_id: int, _: User = Depends(require_manager), db: AsyncSession = Depends(get_db)) -> BotDetail:
    bot = await _get_bot_or_404(db, bot_id)
    return BotDetail(
        **BotOut.model_validate(bot).model_dump(),
        counts=await bot_service.counts(db, bot.id),
        deep_link=bot_service.deep_link(bot, None),
    )


@router.delete("/{bot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_bot(bot_id: int, _: User = Depends(require_manager), db: AsyncSession = Depends(get_db)) -> None:
    bot = await _get_bot_or_404(db, bot_id)
    try:
        await engine_client.bot_stop(bot.id, bot.token)
    except engine_client.EngineUnavailable:
        pass
    await db.delete(bot)
    await db.commit()


@router.post("/{bot_id}/start", response_model=BotOut)
async def start_bot(bot_id: int, user: User = Depends(require_manager), db: AsyncSession = Depends(get_db)) -> BotOut:
    bot = await _get_bot_or_404(db, bot_id)
    try:
        await bot_service.start_bot(db, bot)
    except engine_client.EngineUnavailable as exc:
        raise _engine_error(exc)
    await audit.record_event(db, type="bot.start", actor_type="user", actor_id=user.id, entity_ref=f"bot:{bot.id}")
    return bot


@router.post("/{bot_id}/stop", response_model=BotOut)
async def stop_bot(bot_id: int, _: User = Depends(require_manager), db: AsyncSession = Depends(get_db)) -> BotOut:
    bot = await _get_bot_or_404(db, bot_id)
    await bot_service.stop_bot(db, bot)
    return bot


@router.get("/{bot_id}/deep-link")
async def deep_link(
    bot_id: int, utm: str | None = Query(default=None),
    _: User = Depends(require_manager), db: AsyncSession = Depends(get_db),
) -> dict:
    bot = await _get_bot_or_404(db, bot_id)
    return {"deep_link": bot_service.deep_link(bot, utm)}


@router.get("/{bot_id}/subscribers", response_model=list[SubscriberOut])
async def list_subscribers(bot_id: int, _: User = Depends(require_manager), db: AsyncSession = Depends(get_db)) -> list:
    await _get_bot_or_404(db, bot_id)
    return await bot_service.list_subscribers(db, bot_id)


@router.get("/{bot_id}/conversations", response_model=list[BotConversationOut])
async def list_conversations(bot_id: int, _: User = Depends(require_manager), db: AsyncSession = Depends(get_db)) -> list:
    await _get_bot_or_404(db, bot_id)
    convs = await bot_service.list_conversations(db, bot_id)
    return [await bot_service.conversation_dict(db, c) for c in convs]


@router.get("/{bot_id}/conversations/{conversation_id}", response_model=BotThreadOut)
async def get_thread(
    bot_id: int, conversation_id: int,
    _: User = Depends(require_manager), db: AsyncSession = Depends(get_db),
) -> BotThreadOut:
    await _get_bot_or_404(db, bot_id)
    conv = await _get_conv_or_404(db, conversation_id)
    messages = await bot_service.get_thread(db, conversation_id)
    return BotThreadOut(
        conversation=BotConversationOut(**await bot_service.conversation_dict(db, conv)),
        messages=[BotMessageOut(**bot_service.message_dict(m)) for m in messages],
    )


@router.post("/{bot_id}/conversations/{conversation_id}/read", response_model=BotConversationOut)
async def mark_read(
    bot_id: int, conversation_id: int,
    _: User = Depends(require_manager), db: AsyncSession = Depends(get_db),
) -> BotConversationOut:
    await _get_bot_or_404(db, bot_id)
    conv = await _get_conv_or_404(db, conversation_id)
    await bot_service.mark_read(db, conv)
    return BotConversationOut(**await bot_service.conversation_dict(db, conv))


@router.post("/{bot_id}/conversations/{conversation_id}/reply", response_model=BotMessageOut)
async def reply(
    bot_id: int, conversation_id: int, payload: ReplyRequest,
    user: User = Depends(require_manager), db: AsyncSession = Depends(get_db),
) -> BotMessageOut:
    bot = await _get_bot_or_404(db, bot_id)
    conv = await _get_conv_or_404(db, conversation_id)
    try:
        message = await bot_service.reply(db, bot, conv, user.id, payload.text)
    except engine_client.EngineUnavailable as exc:
        raise _engine_error(exc)
    await bot_service.broadcast_message_event(db, conv, message)
    return BotMessageOut(**bot_service.message_dict(message))


@router.post("/{bot_id}/send")
async def send(
    bot_id: int, payload: SendRequest,
    _: User = Depends(require_manager), db: AsyncSession = Depends(get_db),
) -> dict:
    bot = await _get_bot_or_404(db, bot_id)
    try:
        return await engine_client.bot_send(bot.id, bot.token, payload.chat_id, payload.text)
    except engine_client.EngineUnavailable as exc:
        raise _engine_error(exc)


@router.post("/{bot_id}/post")
async def post(
    bot_id: int, payload: PostRequest,
    user: User = Depends(require_manager), db: AsyncSession = Depends(get_db),
) -> dict:
    bot = await _get_bot_or_404(db, bot_id)
    try:
        result = await engine_client.bot_post(
            bot.id, bot.token, payload.chat_id, payload.text, payload.image_url
        )
    except engine_client.EngineUnavailable as exc:
        raise _engine_error(exc)
    await audit.record_event(db, type="bot.post", actor_type="user", actor_id=user.id, entity_ref=f"bot:{bot.id}")
    return result


@router.post("/{bot_id}/broadcast")
async def broadcast(
    bot_id: int, payload: BroadcastRequest,
    user: User = Depends(require_manager), db: AsyncSession = Depends(get_db),
) -> dict:
    bot = await _get_bot_or_404(db, bot_id)
    result = await bot_service.broadcast(db, bot, payload.text)
    await audit.record_event(db, type="bot.broadcast", actor_type="user", actor_id=user.id, entity_ref=f"bot:{bot.id}", meta=result)
    return result


@router.post("/{bot_id}/simulate-incoming", response_model=BotConversationOut)
async def simulate_incoming(
    bot_id: int, payload: SimulateBotIncoming,
    _: User = Depends(require_manager), db: AsyncSession = Depends(get_db),
) -> BotConversationOut:
    """Dev/test: inject a bot message (same path the engine listener drives)."""
    await _get_bot_or_404(db, bot_id)
    conv, message = await bot_service.record_incoming(
        db, bot_id, payload.telegram_user_id, payload.name, payload.text, utm=payload.utm_source
    )
    await bot_service.broadcast_message_event(db, conv, message)
    return BotConversationOut(**await bot_service.conversation_dict(db, conv))
