from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models import AuthSession, User
from app.services.auth_sessions import get_session_user


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login/verify", auto_error=False)


async def get_optional_current_user(
    request: Request, db: AsyncSession = Depends(get_db), token: str | None = Depends(oauth2_scheme)
) -> User | None:
    if not token:
        return await get_session_user(request, db)
    claims = decode_access_token(token)
    if claims is None:
        return None
    auth_session = await db.scalar(
        select(AuthSession)
        .options(selectinload(AuthSession.user))
        .where(
            AuthSession.id == claims.session_id,
            AuthSession.user_id == claims.user_id,
            AuthSession.expires_at > datetime.now(UTC),
        )
    )
    if auth_session is None or not auth_session.user.is_active:
        return None
    return auth_session.user


async def get_current_user(user: User | None = Depends(get_optional_current_user)) -> User:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )
    return user
