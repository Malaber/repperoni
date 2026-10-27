import asyncio
import base64
import hashlib
from contextlib import closing
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
from sqlalchemy import delete
from starlette.requests import HTTPConnection

from app.core.database import SessionLocal
from app.main import app
from app.models import MobileAuthorization
from app.services.auth_sessions import create_auth_session
from tests.conftest import create_user


async def browser_session(user):
    from itsdangerous import TimestampSigner
    from app.core.config import settings
    import json

    request = HTTPConnection({"type": "http", "session": {}})
    async with SessionLocal() as db:
        await create_auth_session(request, db, user)
    data = base64.b64encode(json.dumps(request.session).encode())
    return TimestampSigner(settings.secret_key_value).sign(data).decode()


def test_pkce_user_scope_replay_and_revocation(user):
    verifier = "v" * 43
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    )
    params = {"state": "s" * 43, "code_challenge": challenge}
    with TestClient(app, headers={"X-Repperoni-CSRF": "1"}, follow_redirects=False) as client:
        response = client.get("/api/v1/auth/mobile/authorize", params=params)
        assert response.status_code == 303
        assert response.headers["location"].startswith("/login?next=")
        assert client.get("/api/v1/auth/mobile/authorize", params={}).status_code == 422
        client.cookies.set("repperoni-session", asyncio.run(browser_session(user)))
        response = client.get("/api/v1/auth/mobile/authorize", params=params)
        callback = urlparse(response.headers["location"])
        assert callback.scheme == "de.malaber.repperoni"
        values = parse_qs(callback.query)
        assert values["state"] == [params["state"]]
        assert "access_token" not in values
        body = {"code": values["code"][0], "code_verifier": verifier}
        assert (
            client.post(
                "/api/v1/auth/mobile/token", json={**body, "code_verifier": "x" * 43}
            ).status_code
            == 401
        )
        response = client.post("/api/v1/auth/mobile/token", json=body)
        assert response.status_code == 200
        assert response.json()["user_id"] == str(user.id)
        assert client.post("/api/v1/auth/mobile/token", json=body).status_code == 401
        token = response.json()["access_token"]
        client.cookies.clear()
        client.headers["Authorization"] = f"Bearer {token}"
        workout = client.post("/api/v1/workouts", json={}).json()
        assert client.get(f"/api/v1/workouts/{workout['id']}").status_code == 200
        other = asyncio.run(create_user())
        client.headers.pop("Authorization")
        client.cookies.set("repperoni-session", asyncio.run(browser_session(other)))
        assert client.get(f"/api/v1/workouts/{workout['id']}").status_code == 404
        client.cookies.clear()
        client.headers["Authorization"] = f"Bearer {token}"
        assert client.post("/api/v1/auth/logout").status_code == 200
        assert client.get("/api/v1/workouts").status_code == 401


def test_mobile_expired_and_inactive_grants(user):
    async def grant(expired=False, inactive=False):
        async with SessionLocal() as db:
            from app.models import User

            record = await db.get(User, user.id)
            record.is_active = not inactive
            await db.execute(delete(MobileAuthorization))
            db.add(
                MobileAuthorization(
                    code_hash=hashlib.sha256(b"c" * 43).hexdigest(),
                    user_id=user.id,
                    challenge=base64.urlsafe_b64encode(hashlib.sha256(b"v" * 43).digest())
                    .decode()
                    .rstrip("="),
                    expires_at=datetime.now(UTC) + timedelta(seconds=-1 if expired else 120),
                )
            )
            await db.commit()

    with TestClient(app, headers={"X-Repperoni-CSRF": "1"}) as client:
        for expired, inactive in [(True, False), (False, True)]:
            asyncio.run(grant(expired, inactive))
            response = client.post(
                "/api/v1/auth/mobile/token", json={"code": "c" * 43, "code_verifier": "v" * 43}
            )
            assert response.status_code == 401


def test_mobile_migration_round_trip(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from app.core.config import settings
    import sqlite3

    database = tmp_path / "mobile.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{database}")
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    with closing(sqlite3.connect(database)) as connection:
        assert connection.execute("PRAGMA table_info(mobile_authorizations)").fetchall()
    command.downgrade(config, "0006_set_mutation_ledger")
    command.upgrade(config, "head")
