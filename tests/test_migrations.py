import sqlite3
import uuid
from contextlib import closing

from alembic import command
from alembic.config import Config

from app.core.config import settings


def test_registration_policy_migrates_existing_owner(tmp_path, monkeypatch):
    database = tmp_path / "migration.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{database}")
    config = Config("alembic.ini")
    command.upgrade(config, "0001_initial")

    user_id = uuid.uuid4().hex
    passkey_id = uuid.uuid4().hex
    with closing(sqlite3.connect(database)) as connection:
        connection.execute(
            "INSERT INTO users (id, email, display_name) VALUES (?, ?, ?)",
            (user_id, "owner@example.com", "Existing Owner"),
        )
        connection.execute(
            """
            INSERT INTO passkeys
                (id, user_id, name, credential_id, public_key, sign_count)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (passkey_id, user_id, "Phone", "existing-key", b"public-key", 0),
        )
        connection.commit()

    command.upgrade(config, "head")

    with closing(sqlite3.connect(database)) as connection:
        owner = connection.execute(
            "SELECT registration_slot, is_admin FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        passkey_owner = connection.execute(
            "SELECT user_id FROM passkeys WHERE id = ?",
            (passkey_id,),
        ).fetchone()
        indexes = connection.execute("PRAGMA index_list('users')").fetchall()
        unique_index_columns = {
            tuple(
                row[2] for row in connection.execute(f"PRAGMA index_info('{index[1]}')").fetchall()
            )
            for index in indexes
            if index[2] == 1
        }
    assert owner == (1, 1)
    assert passkey_owner == (user_id,)
    assert ("registration_slot",) in unique_index_columns
