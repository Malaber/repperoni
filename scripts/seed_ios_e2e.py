"""CLI-only fixture: never imported by the application server."""
import asyncio
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{ROOT / '.tmp' / 'e2e.db'}"
os.environ["SECRET_KEY"] = "repperoni-local-e2e-secret-not-for-production"

from app.core.database import SessionLocal  # noqa: E402
from app.core.security import create_access_token  # noqa: E402
from app.models import AuthSession, User  # noqa: E402


async def main():
    async with SessionLocal() as db:
        user = User(email="ios-e2e@example.com", display_name="Native Mozzarella")
        db.add(user)
        await db.flush()
        now = datetime.now(UTC)
        session = AuthSession(user_id=user.id, last_seen_at=now, expires_at=now + timedelta(hours=1))
        db.add(session)
        await db.commit()
        fixture = {"token": create_access_token(user.id, session.id), "server": "http://127.0.0.1:8017"}
        path = ROOT / "ios/RepperoniIOS/UITests/Fixture.json"
        path.write_text(json.dumps(fixture))


asyncio.run(main())
