from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from jwt.exceptions import InvalidTokenError

from app.core.config import settings

# Public JWT metadata, not credentials.
TOKEN_ALGORITHM = "HS256"  # nosec B105
TOKEN_AUDIENCE = "repperoni-api"  # nosec B105
TOKEN_ISSUER = "repperoni"  # nosec B105


@dataclass(frozen=True)
class AccessTokenClaims:
    user_id: UUID
    session_id: UUID


def create_access_token(user_id: UUID, session_id: UUID) -> str:
    issued_at = datetime.now(UTC)
    expires_at = issued_at + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode(
        {
            "aud": TOKEN_AUDIENCE,
            "exp": expires_at,
            "iat": issued_at,
            "iss": TOKEN_ISSUER,
            "sid": str(session_id),
            "sub": str(user_id),
        },
        settings.secret_key_value,
        algorithm=TOKEN_ALGORITHM,
    )


def decode_access_token(token: str) -> AccessTokenClaims | None:
    try:
        payload = jwt.decode(
            token,
            settings.secret_key_value,
            algorithms=[TOKEN_ALGORITHM],
            audience=TOKEN_AUDIENCE,
            issuer=TOKEN_ISSUER,
            options={
                "require": ["aud", "exp", "iat", "iss", "sid", "sub"],
                "strict_aud": True,
            },
        )
        return AccessTokenClaims(
            user_id=UUID(payload["sub"]),
            session_id=UUID(payload["sid"]),
        )
    except InvalidTokenError, KeyError, TypeError, ValueError:
        return None
