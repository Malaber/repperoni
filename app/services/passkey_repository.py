from datetime import UTC, datetime
from secrets import compare_digest
from unicodedata import normalize
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastpasskey import PasskeyConflictError, PasskeyCredential
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import RegistrationMode, settings
from app.core.database import get_db
from app.core.security import create_access_token, decode_access_token
from app.models import Passkey, User
from app.services.auth_sessions import (
    create_auth_session,
    revoke_auth_session,
    revoke_auth_session_id,
)


REGISTRATION_ROUTE_SUFFIXES = frozenset(
    {
        "/auth/register/options",
        "/auth/register/verify",
    }
)
REGISTRATION_BOOTSTRAP_HEADER = "X-Repperoni-Registration-Token"


class RegistrationUnavailableError(Exception):
    """The configured self-registration policy rejected a new account."""


def normalize_registration_email(raw_email: str) -> str:
    email = normalize("NFKC", raw_email).strip().casefold()
    if not email:
        raise ValueError("Email is required")
    if len(email) > 255:
        raise ValueError("Email must be at most 255 characters")
    return email


def normalize_registration_display_name(raw_name: str) -> str:
    display_name = " ".join(normalize("NFKC", raw_name).split())
    if not display_name:
        raise ValueError("Display name is required")
    if len(display_name) > 120:
        raise ValueError("Display name must be at most 120 characters")
    return display_name


def _new_passkey(user_id: UUID | None, name: str, credential: PasskeyCredential) -> Passkey:
    now = datetime.now(UTC)
    record = Passkey(
        name=name,
        credential_id=credential.credential_id,
        public_key=credential.public_key,
        sign_count=credential.sign_count,
        created_at=now,
        last_used_at=now,
    )
    if user_id is not None:
        record.user_id = user_id
    return record


class RepperoniPasskeyRepository:
    def __init__(
        self,
        db: AsyncSession,
        *,
        registration_mode: RegistrationMode | None = None,
    ) -> None:
        self.db = db
        self.registration_mode = registration_mode or settings.registration_mode
        self.auth_session_id: UUID | None = None

    async def ensure_registration_allowed(self) -> None:
        if self.registration_mode == "open":
            return
        if self.registration_mode == "closed":
            raise RegistrationUnavailableError
        existing_user = await self.db.scalar(select(User.id).limit(1))
        if existing_user is not None:
            raise RegistrationUnavailableError

    async def user_by_email(self, email: str) -> User | None:
        email = normalize_registration_email(email)
        result = await self.db.execute(
            select(User)
            .options(selectinload(User.passkeys))
            .where(User.email == email)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def user_by_id(self, user_id: UUID) -> User | None:
        result = await self.db.execute(
            select(User)
            .options(selectinload(User.passkeys))
            .where(User.id == user_id)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def passkey_by_credential_id(self, credential_id: str) -> Passkey | None:
        result = await self.db.execute(
            select(Passkey)
            .join(Passkey.user)
            .options(selectinload(Passkey.user))
            .where(Passkey.credential_id == credential_id, User.is_active.is_(True))
        )
        return result.scalar_one_or_none()

    async def register_user(
        self,
        *,
        user_id: UUID,
        email: str,
        display_name: str,
        passkey_name: str,
        credential: PasskeyCredential,
    ) -> User:
        try:
            await self.ensure_registration_allowed()
        except RegistrationUnavailableError as exc:
            raise PasskeyConflictError from exc
        normalized_email = normalize_registration_email(email)
        normalized_display_name = normalize_registration_display_name(display_name)
        first_user = self.registration_mode == "first-user"
        user = User(
            id=user_id,
            email=normalized_email,
            display_name=normalized_display_name,
            is_admin=first_user,
            registration_slot=1 if first_user else None,
        )
        user.passkeys.append(_new_passkey(None, passkey_name, credential))
        self.db.add(user)
        try:
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise PasskeyConflictError from exc
        return await self.user_by_id(user.id)

    async def replace_passkeys(
        self, *, user_id: UUID, passkey_name: str, credential: PasskeyCredential
    ) -> User:
        await self.db.execute(delete(Passkey).where(Passkey.user_id == user_id))
        self.db.add(_new_passkey(user_id, passkey_name, credential))
        await self.db.commit()
        user = await self.user_by_id(user_id)
        if user is None:
            raise RuntimeError("User disappeared while replacing passkeys")
        return user

    async def add_passkey(
        self, *, user_id: UUID, name: str, credential: PasskeyCredential
    ) -> Passkey:
        record = _new_passkey(user_id, name, credential)
        self.db.add(record)
        await self.db.commit()
        await self.db.refresh(record)
        return record

    async def record_passkey_use(self, passkey: Passkey, *, new_sign_count: int) -> None:
        passkey.sign_count = new_sign_count
        passkey.last_used_at = datetime.now(UTC)
        await self.db.commit()

    async def rename_passkey(self, passkey: Passkey, *, name: str, new_sign_count: int) -> Passkey:
        passkey.name = name
        passkey.sign_count = new_sign_count
        passkey.last_used_at = datetime.now(UTC)
        await self.db.commit()
        await self.db.refresh(passkey)
        return passkey

    async def delete_passkey(
        self, *, user_id: UUID, passkey_id: UUID, confirming_passkey: Passkey, new_sign_count: int
    ) -> None:
        confirming_passkey.sign_count = new_sign_count
        confirming_passkey.last_used_at = datetime.now(UTC)
        await self.db.flush()
        await self.db.execute(
            delete(Passkey).where(Passkey.id == passkey_id, Passkey.user_id == user_id)
        )
        await self.db.commit()

    async def authenticate(self, request: Request, user: User) -> User:
        self.auth_session_id = await create_auth_session(request, self.db, user)
        return user

    async def logout(self, request: Request) -> None:
        await revoke_auth_session(request, self.db)
        authorization = request.headers.get("Authorization", "")
        scheme, _, token = authorization.partition(" ")
        if scheme.casefold() == "bearer" and token:
            claims = decode_access_token(token)
            if claims is not None:
                await revoke_auth_session_id(self.db, claims.session_id)

    def access_token(self, user: User) -> str:
        if self.auth_session_id is None:
            raise RuntimeError("Access token requested before authentication")
        return create_access_token(user.id, self.auth_session_id)


async def get_passkey_repository(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> RepperoniPasskeyRepository:
    repository = RepperoniPasskeyRepository(db)
    route = request.scope.get("route")
    route_path = getattr(route, "path", request.url.path)
    if any(route_path.endswith(suffix) for suffix in REGISTRATION_ROUTE_SUFFIXES):
        configured_token = settings.registration_bootstrap_token
        if settings.registration_mode == "first-user" and configured_token is not None:
            supplied_token = request.headers.get(REGISTRATION_BOOTSTRAP_HEADER, "")
            if not compare_digest(
                supplied_token.encode(),
                configured_token.get_secret_value().encode(),
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Registration is not available",
                )
        try:
            await repository.ensure_registration_allowed()
        except RegistrationUnavailableError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Registration is not available",
            ) from exc

        if route_path.endswith("/auth/register/options"):
            try:
                payload = await request.json()
            except ValueError:
                payload = None
            if isinstance(payload, dict):
                try:
                    if isinstance(payload.get("email"), str):
                        payload["email"] = normalize_registration_email(payload["email"])
                    if isinstance(payload.get("display_name"), str):
                        payload["display_name"] = normalize_registration_display_name(
                            payload["display_name"]
                        )
                except ValueError as exc:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                        detail=str(exc),
                    ) from exc
    return repository
