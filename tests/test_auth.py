import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from fastpasskey import PasskeyCredential
from fastapi import HTTPException
from jose import jwt
from starlette.requests import Request

from app.api.deps import get_current_user, get_optional_current_user
from app.api.v1.routes.auth import SAFE_ROUTE_PATHS, passkey_router
from app.core.config import Settings, settings
from app.core.database import SessionLocal
from app.core.security import TOKEN_ALGORITHM, TOKEN_AUDIENCE, TOKEN_ISSUER, create_access_token
from app.models import AuthSession, Passkey
from app.services.auth_sessions import SESSION_KEY, get_session_user, revoke_auth_session
from app.services.passkey_repository import RepperoniPasskeyRepository


def request_with_session(values=None):
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
    request.scope["session"] = dict(values or {})
    return request


def test_access_token_contains_user_id():
    user_id = uuid.uuid4()
    token = create_access_token(user_id)
    payload = jwt.decode(
        token,
        settings.secret_key,
        algorithms=[TOKEN_ALGORITHM],
        audience=TOKEN_AUDIENCE,
        issuer=TOKEN_ISSUER,
    )
    assert payload["sub"] == str(user_id)
    assert payload["iat"] < payload["exp"]
    assert payload["exp"] - payload["iat"] == 60 * 60


def test_passkey_repository_lifecycle(user):
    async def scenario():
        credential = PasskeyCredential("credential-1", b"public-key", 1)
        async with SessionLocal() as db:
            repository = RepperoniPasskeyRepository(db)
            assert await repository.user_by_email("missing@example.com") is None
            passkey = await repository.add_passkey(
                user_id=user.id, name="Phone", credential=credential
            )
            assert (await repository.passkey_by_credential_id("credential-1")).id == passkey.id
            await repository.record_passkey_use(passkey, new_sign_count=2)
            renamed = await repository.rename_passkey(passkey, name="Gym phone", new_sign_count=3)
            assert renamed.name == "Gym phone"
            request = request_with_session()
            await repository.authenticate(request, user)
            assert SESSION_KEY in request.session
            assert repository.access_token(user)
            await repository.logout(request)
            assert SESSION_KEY not in request.session

    asyncio.run(scenario())


def test_passkey_repository_registration_replace_and_delete():
    async def scenario():
        async with SessionLocal() as db:
            repository = RepperoniPasskeyRepository(db)
            user_id = uuid.uuid4()
            first = PasskeyCredential("registered-1", b"first-key", 0)
            registered = await repository.register_user(
                user_id=user_id,
                email=f"{user_id}@example.com",
                display_name="Registered Lifter",
                passkey_name="Phone",
                credential=first,
            )
            assert registered.id == user_id
            assert (await repository.user_by_id(user_id)).passkeys[0].name == "Phone"

            second = PasskeyCredential("registered-2", b"second-key", 1)
            replaced = await repository.replace_passkeys(
                user_id=user_id, passkey_name="Laptop", credential=second
            )
            assert [item.name for item in replaced.passkeys] == ["Laptop"]

            third = await repository.add_passkey(
                user_id=user_id,
                name="Watch",
                credential=PasskeyCredential("registered-3", b"third-key", 0),
            )
            confirming = await repository.passkey_by_credential_id("registered-2")
            await repository.delete_passkey(
                user_id=user_id,
                passkey_id=third.id,
                confirming_passkey=confirming,
                new_sign_count=2,
            )
            loaded = await repository.user_by_id(user_id)
            assert [item.name for item in loaded.passkeys] == ["Laptop"]

    asyncio.run(scenario())


def test_invalid_and_expired_sessions_are_cleared(user):
    async def scenario():
        async with SessionLocal() as db:
            invalid = request_with_session({SESSION_KEY: "not-a-uuid"})
            assert await get_session_user(invalid, db) is None
            assert not invalid.session

            expired = AuthSession(
                user_id=user.id,
                last_seen_at=datetime.now(UTC) - timedelta(days=40),
                expires_at=datetime.now(UTC) - timedelta(days=1),
            )
            db.add(expired)
            await db.commit()
            await db.refresh(expired)
            request = request_with_session({SESSION_KEY: str(expired.id)})
            assert await get_session_user(request, db) is None
            assert not request.session

            empty = request_with_session()
            await revoke_auth_session(empty, db)
            missing = request_with_session({SESSION_KEY: str(uuid.uuid4())})
            await revoke_auth_session(missing, db)

    asyncio.run(scenario())


def test_inactive_users_lose_sessions_and_passkey_login(user):
    async def scenario():
        async with SessionLocal() as db:
            auth_session = AuthSession(
                user_id=user.id,
                last_seen_at=datetime.now(UTC),
                expires_at=datetime.now(UTC) + timedelta(days=1),
            )
            passkey = Passkey(
                user_id=user.id,
                name="Disabled phone",
                credential_id=f"disabled-{uuid.uuid4()}",
                public_key=b"not-used",
                sign_count=0,
            )
            db.add_all([auth_session, passkey])
            await db.commit()
            await db.refresh(auth_session)
            await db.refresh(passkey)

            stored_user = await db.get(type(user), user.id)
            stored_user.is_active = False
            await db.commit()

            request = request_with_session({SESSION_KEY: str(auth_session.id)})
            assert await get_session_user(request, db) is None
            assert not request.session
            assert await db.get(AuthSession, auth_session.id) is None

            repository = RepperoniPasskeyRepository(db)
            assert await repository.passkey_by_credential_id(passkey.credential_id) is None

    asyncio.run(scenario())


def test_passkey_options_endpoint_uses_shared_module(client):
    response = client.post(
        "/api/v1/auth/register/options",
        json={"email": f"{uuid.uuid4()}@example.com", "display_name": "Pepper"},
    )
    assert response.status_code == 200
    assert response.json()["rp"]["name"] == "Repperoni"
    assert response.json()["rp"]["id"] == "localhost"

    login = client.post("/api/v1/auth/login/options", json={})
    assert login.status_code == 200
    assert "challenge" in login.json()


def test_unprotected_passkey_enrollment_routes_are_not_exposed(client):
    exposed_paths = {route.path for route in passkey_router().routes}
    assert exposed_paths == SAFE_ROUTE_PATHS
    assert client.post("/api/v1/auth/settings/passkey/options").status_code == 404
    assert (
        client.post(
            "/api/v1/auth/passkeys/register/options",
            json={"name": "Attacker passkey"},
        ).status_code
        == 404
    )


def test_bearer_and_optional_auth_dependencies(user):
    async def scenario():
        request = request_with_session()
        async with SessionLocal() as db:
            assert await get_optional_current_user(request, db, None) is None
            assert await get_optional_current_user(request, db, "not-a-jwt") is None
            legacy_token = jwt.encode(
                {
                    "sub": str(user.id),
                    "exp": datetime.now(UTC) + timedelta(minutes=5),
                },
                settings.secret_key,
                algorithm=TOKEN_ALGORITHM,
            )
            assert await get_optional_current_user(request, db, legacy_token) is None
            token = create_access_token(user.id)
            assert (await get_optional_current_user(request, db, token)).id == user.id
        try:
            await get_current_user(None)
        except HTTPException as exc:
            assert exc.status_code == 401
        else:
            raise AssertionError("Missing authentication should fail")

    asyncio.run(scenario())


def test_settings_normalize_urls_and_lists():
    configured = Settings(
        app_base_url="https://repperoni.example/",
        cors_origins="https://ios.example, https://web.example",
        webcredentials_apps="TEAM.app",
    )
    assert configured.app_base_url == "https://repperoni.example"
    assert configured.cors_origins == ["https://ios.example", "https://web.example"]
    assert configured.webcredentials_apps == ["TEAM.app"]
