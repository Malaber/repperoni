import sqlite3
import uuid
from contextlib import closing

import pytest
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


def test_workout_integrity_migration_repairs_and_constrains_rows(tmp_path, monkeypatch):
    database = tmp_path / "workout-integrity.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{database}")
    config = Config("alembic.ini")
    command.upgrade(config, "0002_registration_policy")

    user_id = uuid.uuid4().hex
    older_workout = uuid.uuid4().hex
    newer_workout = uuid.uuid4().hex
    first_station = uuid.uuid4().hex
    second_station = uuid.uuid4().hex
    with closing(sqlite3.connect(database)) as connection:
        connection.execute(
            "INSERT INTO users (id, email, display_name) VALUES (?, ?, ?)",
            (user_id, "lifter@example.com", "Lifter"),
        )
        connection.executemany(
            """
            INSERT INTO workouts (id, user_id, name, started_at, completed_at)
            VALUES (?, ?, ?, ?, NULL)
            """,
            [
                (older_workout, user_id, "Older", "2026-01-01 10:00:00"),
                (newer_workout, user_id, "Newer", "2026-01-02 10:00:00"),
            ],
        )
        connection.executemany(
            """
            INSERT INTO workout_stations
                (id, workout_id, exercise_id, position, started_at)
            VALUES (?, ?, ?, 1, ?)
            """,
            [
                (
                    first_station,
                    newer_workout,
                    "11111111111141118111111111111111",
                    "2026-01-02 10:01:00",
                ),
                (
                    second_station,
                    newer_workout,
                    "22222222222242228222222222222222",
                    "2026-01-02 10:02:00",
                ),
            ],
        )
        connection.commit()

    command.upgrade(config, "head")

    with closing(sqlite3.connect(database)) as connection:
        active = connection.execute(
            "SELECT id FROM workouts WHERE user_id = ? AND completed_at IS NULL",
            (user_id,),
        ).fetchall()
        positions = connection.execute(
            """
            SELECT position
            FROM workout_stations
            WHERE workout_id = ?
            ORDER BY position
            """,
            (newer_workout,),
        ).fetchall()
        assert active == [(newer_workout,)]
        assert positions == [(1,), (2,)]

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO workouts (id, user_id, name, started_at, completed_at)
                VALUES (?, ?, ?, ?, NULL)
                """,
                (uuid.uuid4().hex, user_id, "Duplicate", "2026-01-03 10:00:00"),
            )
        connection.rollback()
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO workout_stations
                    (id, workout_id, exercise_id, position, started_at)
                VALUES (?, ?, ?, 2, ?)
                """,
                (
                    uuid.uuid4().hex,
                    newer_workout,
                    "33333333333343338333333333333333",
                    "2026-01-02 10:03:00",
                ),
            )


def test_passkey_ceremony_claim_migration_enforces_single_use(tmp_path, monkeypatch):
    database = tmp_path / "passkey-ceremony-claims.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{database}")
    config = Config("alembic.ini")
    command.upgrade(config, "0003_workout_integrity")
    command.upgrade(config, "head")

    digest = b"x" * 32
    with closing(sqlite3.connect(database)) as connection:
        connection.execute(
            """
            INSERT INTO passkey_ceremony_claims
                (challenge_digest, expires_at)
            VALUES (?, ?)
            """,
            (digest, "2026-01-01 10:00:00"),
        )
        connection.commit()
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO passkey_ceremony_claims
                    (challenge_digest, expires_at)
                VALUES (?, ?)
                """,
                (digest, "2026-01-01 10:00:00"),
            )


def test_exercise_name_key_migration_repairs_case_variants(tmp_path, monkeypatch):
    database = tmp_path / "exercise-name-keys.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{database}")
    config = Config("alembic.ini")
    command.upgrade(config, "0004_passkey_ceremony_claims")

    user_id = uuid.uuid4().hex
    with closing(sqlite3.connect(database)) as connection:
        connection.execute(
            "INSERT INTO users (id, email, display_name) VALUES (?, ?, ?)",
            (user_id, "names@example.com", "Names"),
        )
        connection.executemany(
            """
            INSERT INTO exercises
                (id, user_id, name, muscle_group, equipment)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (uuid.uuid4().hex, user_id, "Pepper Press", "Core", "Pizza"),
                (uuid.uuid4().hex, user_id, "pepper press", "Core", "Pizza"),
            ],
        )
        connection.commit()

    command.upgrade(config, "head")

    with closing(sqlite3.connect(database)) as connection:
        rows = connection.execute(
            """
            SELECT name, name_key
            FROM exercises
            WHERE user_id = ?
            ORDER BY name
            """,
            (user_id,),
        ).fetchall()
        assert len(rows) == 2
        assert len({name for name, _ in rows}) == 2
        assert len({name_key for _, name_key in rows}) == 2
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO exercises
                    (id, user_id, name, name_key, muscle_group, equipment)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    uuid.uuid4().hex,
                    user_id,
                    "PEPPER PRESS",
                    "pepper press",
                    "Core",
                    "Pizza",
                ),
            )


def test_set_mutation_migration_backfills_deletion_tombstones(tmp_path, monkeypatch):
    database = tmp_path / "set-mutations.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{database}")
    config = Config("alembic.ini")
    command.upgrade(config, "0005_exercise_name_keys")

    user_id = uuid.uuid4().hex
    workout_id = uuid.uuid4().hex
    station_id = uuid.uuid4().hex
    set_id = uuid.uuid4().hex
    mutation_id = str(uuid.uuid4())
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(
            "INSERT INTO users (id, email, display_name) VALUES (?, ?, ?)",
            (user_id, "mutations@example.com", "Mutations"),
        )
        connection.execute(
            """
            INSERT INTO workouts (id, user_id, name, started_at)
            VALUES (?, ?, ?, ?)
            """,
            (workout_id, user_id, "Workout", "2026-01-01 10:00:00"),
        )
        connection.execute(
            """
            INSERT INTO workout_stations
                (id, workout_id, exercise_id, position, started_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                station_id,
                workout_id,
                "11111111111141118111111111111111",
                1,
                "2026-01-01 10:01:00",
            ),
        )
        connection.execute(
            """
            INSERT INTO set_entries (
                id,
                user_id,
                station_id,
                set_number,
                weight_kg,
                reps,
                completed_at,
                client_mutation_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                set_id,
                user_id,
                station_id,
                1,
                42,
                6,
                "2026-01-01 10:02:00",
                mutation_id,
            ),
        )
        connection.commit()

    command.upgrade(config, "head")

    with closing(sqlite3.connect(database)) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        mutation = connection.execute("""
            SELECT user_id, client_mutation_id, station_id, set_id, weight_kg, reps
            FROM set_mutations
            """).fetchone()
        assert mutation == (
            user_id,
            mutation_id,
            station_id,
            set_id,
            42,
            6,
        )
        connection.execute("DELETE FROM set_entries WHERE id = ?", (set_id,))
        connection.commit()
        assert connection.execute("SELECT set_id FROM set_mutations").fetchone() == (None,)
