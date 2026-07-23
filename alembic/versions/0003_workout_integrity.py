"""enforce workout and station ordering invariants

Revision ID: 0003_workout_integrity
Revises: 0002_registration_policy
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_workout_integrity"
down_revision = "0002_registration_policy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY user_id
                           ORDER BY started_at DESC, id DESC
                       ) AS active_rank
                FROM workouts
                WHERE completed_at IS NULL
            )
            UPDATE workouts
            SET completed_at = started_at
            WHERE id IN (
                SELECT id
                FROM ranked
                WHERE active_rank > 1
            )
            """
        )
    )
    op.create_index(
        "uq_workouts_user_active",
        "workouts",
        ["user_id"],
        unique=True,
        sqlite_where=sa.text("completed_at IS NULL"),
        postgresql_where=sa.text("completed_at IS NULL"),
    )

    op.execute(
        sa.text(
            """
            WITH ordered AS (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY workout_id
                           ORDER BY position ASC, started_at ASC, id ASC
                       ) AS normalized_position
                FROM workout_stations
            )
            UPDATE workout_stations
            SET position = (
                SELECT normalized_position
                FROM ordered
                WHERE ordered.id = workout_stations.id
            )
            """
        )
    )
    with op.batch_alter_table("workout_stations") as batch_op:
        batch_op.create_unique_constraint(
            "uq_station_workout_position",
            ["workout_id", "position"],
        )


def downgrade() -> None:
    with op.batch_alter_table("workout_stations") as batch_op:
        batch_op.drop_constraint("uq_station_workout_position", type_="unique")
    op.drop_index("uq_workouts_user_active", table_name="workouts")
