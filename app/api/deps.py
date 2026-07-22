from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models import User
from app.services.auth_sessions import get_session_user


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login/verify", auto_error=False)


async def get_optional_current_user(
    request: Request, db: AsyncSession = Depends(get_db), token: str | None = Depends(oauth2_scheme)
) -> User | None:
    if not token:
        return await get_session_user(request, db)
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        user_id = UUID(payload["sub"])
    except (JWTError, KeyError, TypeError, ValueError):
        return None
    result = await db.execute(select(User).where(User.id == user_id, User.is_active.is_(True)))
    return result.scalar_one_or_none()


async def get_current_user(user: User | None = Depends(get_optional_current_user)) -> User:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )
    return user
