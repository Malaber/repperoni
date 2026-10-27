"""enforce normalized custom exercise names

Revision ID: 0005_exercise_name_keys
Revises: 0004_passkey_ceremony_claims
"""

from unicodedata import normalize

from alembic import op
import sqlalchemy as sa


revision = "0005_exercise_name_keys"
down_revision = "0004_passkey_ceremony_claims"
branch_labels = None
depends_on = None


def _name_key(value: str) -> str:
    return normalize("NFKC", value.strip()).casefold()


def upgrade() -> None:
    with op.batch_alter_table("exercises") as batch_op:
        batch_op.add_column(sa.Column("name_key", sa.String(240), nullable=True))

    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT id, user_id, name
            FROM exercises
            ORDER BY created_at, id
            """
        )
    ).mappings()
    seen: set[tuple[object, str]] = set()
    for row in rows:
        name = row["name"]
        key = _name_key(name)
        identity = (row["user_id"], key)
        if row["user_id"] is not None and identity in seen:
            counter = 2
            while True:
                suffix = f" ({counter})"
                candidate = f"{name[: 120 - len(suffix)].rstrip()}{suffix}"
                key = _name_key(candidate)
                identity = (row["user_id"], key)
                if identity not in seen:
                    name = candidate
                    break
                counter += 1
        seen.add(identity)
        connection.execute(
            sa.text(
                """
                UPDATE exercises
                SET name = :name, name_key = :name_key
                WHERE id = :exercise_id
                """
            ),
            {
                "exercise_id": row["id"],
                "name": name,
                "name_key": key,
            },
        )

    with op.batch_alter_table("exercises") as batch_op:
        batch_op.drop_constraint("uq_exercises_user_name", type_="unique")
        batch_op.alter_column("name_key", existing_type=sa.String(240), nullable=False)
        batch_op.create_unique_constraint(
            "uq_exercises_user_name_key",
            ["user_id", "name_key"],
        )


def downgrade() -> None:
    with op.batch_alter_table("exercises") as batch_op:
        batch_op.drop_constraint("uq_exercises_user_name_key", type_="unique")
        batch_op.drop_column("name_key")
        batch_op.create_unique_constraint(
            "uq_exercises_user_name",
            ["user_id", "name"],
        )
