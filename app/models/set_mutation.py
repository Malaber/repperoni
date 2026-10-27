import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class SetMutation(Base):
    __tablename__ = "set_mutations"
    __table_args__ = (
        UniqueConstraint("user_id", "client_mutation_id", name="uq_set_mutation_user_client"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    client_mutation_id: Mapped[str] = mapped_column(String(120), nullable=False)
    station_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("workout_stations.id", ondelete="CASCADE"),
        nullable=False,
    )
    set_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("set_entries.id", ondelete="SET NULL"),
        nullable=True,
    )
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    reps: Mapped[int] = mapped_column(Integer, nullable=False)
    rpe: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
