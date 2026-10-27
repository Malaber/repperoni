import asyncio
import os
import tempfile
import uuid
from pathlib import Path

TEST_DATABASE = Path(tempfile.gettempdir()) / f"repperoni-pytest-{os.getpid()}.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DATABASE}"
os.environ["ENVIRONMENT"] = "test"
os.environ["REGISTRATION_MODE"] = "open"
os.environ["APP_BASE_URL"] = "http://localhost"
os.environ["WEBAUTHN_RP_ID"] = "localhost"
os.environ["SECRET_KEY"] = "repperoni-pytest-secret-not-for-production"
os.environ["AUTO_MIGRATE"] = "false"

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api.deps import get_current_user  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    for suffix in ("", "-wal", "-shm"):
        Path(f"{TEST_DATABASE}{suffix}").unlink(missing_ok=True)
    command.upgrade(Config("alembic.ini"), "head")
    yield
    for suffix in ("", "-wal", "-shm"):
        Path(f"{TEST_DATABASE}{suffix}").unlink(missing_ok=True)


async def create_user(email: str | None = None) -> User:
    async with SessionLocal() as db:
        user = User(
            id=uuid.uuid4(),
            email=email or f"{uuid.uuid4()}@example.com",
            display_name="Test Lifter",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user


@pytest.fixture
def user() -> User:
    return asyncio.run(create_user())


@pytest.fixture
def client(user: User):
    app.dependency_overrides[get_current_user] = lambda: user
    with TestClient(app, headers={"Origin": "http://localhost"}) as test_client:
        yield test_client
    app.dependency_overrides.clear()
