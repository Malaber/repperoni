"""initial user-scoped workout schema

Revision ID: 0001_initial
Revises:
"""
import uuid

from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


CATALOG = [
    ("11111111-1111-4111-8111-111111111111", "Bench Press", "Chest", "Barbell"),
    ("22222222-2222-4222-8222-222222222222", "Squat", "Legs", "Barbell"),
    ("33333333-3333-4333-8333-333333333333", "Deadlift", "Back", "Barbell"),
    ("44444444-4444-4444-8444-444444444444", "Overhead Press", "Shoulders", "Barbell"),
    ("55555555-5555-4555-8555-555555555555", "Lat Pulldown", "Back", "Cable"),
    ("66666666-6666-4666-8666-666666666666", "Seated Row", "Back", "Cable"),
    ("77777777-7777-4777-8777-777777777777", "Leg Press", "Legs", "Machine"),
    ("88888888-8888-4888-8888-888888888888", "Leg Curl", "Hamstrings", "Machine"),
    ("99999999-9999-4999-8999-999999999999", "Leg Extension", "Quads", "Machine"),
    ("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "Biceps Curl", "Arms", "Dumbbell"),
    ("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", "Triceps Pushdown", "Arms", "Cable"),
    ("cccccccc-cccc-4ccc-8ccc-cccccccccccc", "Calf Raise", "Calves", "Machine"),
]


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "passkeys",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("credential_id", sa.String(255), nullable=False, unique=True),
        sa.Column("public_key", sa.LargeBinary(), nullable=False),
        sa.Column("sign_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_passkeys_user_id", "passkeys", ["user_id"])
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_table(
        "exercises",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("muscle_group", sa.String(80), nullable=False),
        sa.Column("equipment", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "name", name="uq_exercises_user_name"),
    )
    op.create_index("ix_exercises_user_id", "exercises", ["user_id"])
    exercise_table = sa.table(
        "exercises",
        sa.column("id", sa.Uuid()),
        sa.column("user_id", sa.Uuid()),
        sa.column("name", sa.String()),
        sa.column("muscle_group", sa.String()),
        sa.column("equipment", sa.String()),
    )
    op.bulk_insert(
        exercise_table,
        [
            {"id": uuid.UUID(identifier), "user_id": None, "name": name, "muscle_group": group, "equipment": equipment}
            for identifier, name, group, equipment in CATALOG
        ],
    )
    op.create_table(
        "workouts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_workouts_user_started", "workouts", ["user_id", "started_at"])
    op.create_table(
        "workout_stations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workout_id", sa.Uuid(), sa.ForeignKey("workouts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("exercise_id", sa.Uuid(), sa.ForeignKey("exercises.id"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workout_id", "exercise_id", name="uq_station_workout_exercise"),
    )
    op.create_index("ix_workout_stations_workout", "workout_stations", ["workout_id"])
    op.create_table(
        "set_entries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("station_id", sa.Uuid(), sa.ForeignKey("workout_stations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("set_number", sa.Integer(), nullable=False),
        sa.Column("weight_kg", sa.Numeric(8, 2), nullable=False),
        sa.Column("reps", sa.Integer(), nullable=False),
        sa.Column("rpe", sa.Numeric(3, 1)),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("client_mutation_id", sa.String(120)),
        sa.UniqueConstraint("station_id", "set_number", name="uq_set_station_number"),
        sa.UniqueConstraint("user_id", "client_mutation_id", name="uq_set_user_mutation"),
    )
    op.create_index("ix_set_entries_user_completed", "set_entries", ["user_id", "completed_at"])
    op.create_index("ix_set_entries_station", "set_entries", ["station_id"])


def downgrade() -> None:
    op.drop_table("set_entries")
    op.drop_table("workout_stations")
    op.drop_table("workouts")
    op.drop_table("exercises")
    op.drop_table("auth_sessions")
    op.drop_table("passkeys")
    op.drop_table("users")
