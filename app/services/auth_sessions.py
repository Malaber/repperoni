from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.requests import HTTPConnection

from app.core.config import settings
from app.models import AuthSession, User

SESSION_KEY = "auth_session_id"


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


async def create_auth_session(request: HTTPConnection, db: AsyncSession, user: User) -> UUID:
    now = datetime.now(UTC)
    auth_session = AuthSession(
        user_id=user.id,
        last_seen_at=now,
        expires_at=now + timedelta(seconds=settings.session_max_age_seconds),
    )
    db.add(auth_session)
    await db.commit()
    await db.refresh(auth_session)
    request.session.clear()
    request.session[SESSION_KEY] = str(auth_session.id)
    return auth_session.id


async def revoke_auth_session(request: HTTPConnection, db: AsyncSession) -> None:
    raw_id = request.session.pop(SESSION_KEY, None)
    try:
        session_id = UUID(raw_id) if raw_id else None
    except ValueError:
        return
    if session_id and (auth_session := await db.get(AuthSession, session_id)):
        await db.delete(auth_session)
        await db.commit()


async def revoke_auth_session_id(db: AsyncSession, session_id: UUID) -> None:
    if auth_session := await db.get(AuthSession, session_id):
        await db.delete(auth_session)
        await db.commit()


async def get_session_user(request: HTTPConnection, db: AsyncSession) -> User | None:
    raw_id = request.session.get(SESSION_KEY)
    try:
        session_id = UUID(raw_id) if raw_id else None
    except ValueError:
        request.session.pop(SESSION_KEY, None)
        return None
    if session_id is None:
        return None
    result = await db.execute(
        select(AuthSession)
        .options(selectinload(AuthSession.user))
        .where(AuthSession.id == session_id)
    )
    auth_session = result.scalar_one_or_none()
    now = datetime.now(UTC)
    idle_limit = now - timedelta(seconds=settings.session_idle_timeout_seconds)
    if (
        auth_session is None
        or not auth_session.user.is_active
        or _utc(auth_session.expires_at) <= now
        or _utc(auth_session.last_seen_at) <= idle_limit
    ):
        if auth_session is not None:
            await db.delete(auth_session)
            await db.commit()
        request.session.pop(SESSION_KEY, None)
        return None
    auth_session.last_seen_at = now
    await db.commit()
    return auth_session.user
