"""add race-safe first-user registration slot

Revision ID: 0002_registration_policy
Revises: 0001_initial
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_registration_policy"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("registration_slot", sa.Integer(), nullable=True))
        batch_op.create_check_constraint(
            "ck_users_registration_slot",
            "registration_slot IS NULL OR registration_slot = 1",
        )
        batch_op.create_unique_constraint(
            "uq_users_registration_slot",
            ["registration_slot"],
        )

    op.execute(
        sa.text(
            """
            UPDATE users
            SET registration_slot = 1, is_admin = true
            WHERE id = (
                SELECT id
                FROM users
                ORDER BY created_at ASC, id ASC
                LIMIT 1
            )
            """
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint("uq_users_registration_slot", type_="unique")
        batch_op.drop_constraint("ck_users_registration_slot", type_="check")
        batch_op.drop_column("registration_slot")
