from datetime import UTC, datetime, timedelta
from uuid import UUID

from jose import jwt

from app.core.config import settings


TOKEN_ALGORITHM = "HS256"
TOKEN_AUDIENCE = "repperoni-api"
TOKEN_ISSUER = "repperoni"


def create_access_token(user_id: UUID) -> str:
    issued_at = datetime.now(UTC)
    expires_at = issued_at + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode(
        {
            "aud": TOKEN_AUDIENCE,
            "exp": expires_at,
            "iat": issued_at,
            "iss": TOKEN_ISSUER,
            "sub": str(user_id),
        },
        settings.secret_key,
        algorithm=TOKEN_ALGORITHM,
    )
