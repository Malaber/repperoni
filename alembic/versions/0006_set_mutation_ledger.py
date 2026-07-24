"""preserve set mutation identities after deletion

Revision ID: 0006_set_mutation_ledger
Revises: 0005_exercise_name_keys
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_set_mutation_ledger"
down_revision = "0005_exercise_name_keys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "set_mutations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("client_mutation_id", sa.String(120), nullable=False),
        sa.Column(
            "station_id",
            sa.Uuid(),
            sa.ForeignKey("workout_stations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "set_id",
            sa.Uuid(),
            sa.ForeignKey("set_entries.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("weight_kg", sa.Numeric(8, 2), nullable=False),
        sa.Column("reps", sa.Integer(), nullable=False),
        sa.Column("rpe", sa.Numeric(3, 1)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "user_id",
            "client_mutation_id",
            name="uq_set_mutation_user_client",
        ),
    )
    op.create_index(
        "ix_set_mutations_station_id",
        "set_mutations",
        ["station_id"],
    )
    op.execute(
        sa.text(
            """
            INSERT INTO set_mutations (
                id,
                user_id,
                client_mutation_id,
                station_id,
                set_id,
                weight_kg,
                reps,
                rpe,
                created_at
            )
            SELECT
                id,
                user_id,
                client_mutation_id,
                station_id,
                id,
                weight_kg,
                reps,
                rpe,
                completed_at
            FROM set_entries
            WHERE client_mutation_id IS NOT NULL
            """
        )
    )


def downgrade() -> None:
    op.drop_table("set_mutations")
