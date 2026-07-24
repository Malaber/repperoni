"""make passkey ceremonies single use

Revision ID: 0004_passkey_ceremony_claims
Revises: 0003_workout_integrity
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_passkey_ceremony_claims"
down_revision = "0003_workout_integrity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "passkey_ceremony_claims",
        sa.Column("challenge_digest", sa.LargeBinary(32), primary_key=True),
        sa.Column(
            "claimed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_passkey_ceremony_claims_expires_at",
        "passkey_ceremony_claims",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_table("passkey_ceremony_claims")
