import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Workout(Base):
    __tablename__ = "workouts"
    __table_args__ = (
        Index(
            "uq_workouts_user_active",
            "user_id",
            unique=True,
            sqlite_where=text("completed_at IS NULL"),
            postgresql_where=text("completed_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False, default="Workout")
    notes: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user = relationship("User", back_populates="workouts")
    stations = relationship(
        "WorkoutStation",
        back_populates="workout",
        cascade="all, delete-orphan",
        order_by="WorkoutStation.position",
    )


class WorkoutStation(Base):
    __tablename__ = "workout_stations"
    __table_args__ = (
        UniqueConstraint("workout_id", "exercise_id", name="uq_station_workout_exercise"),
        UniqueConstraint("workout_id", "position", name="uq_station_workout_position"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    workout_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("workouts.id", ondelete="CASCADE"), index=True
    )
    exercise_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("exercises.id"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    workout = relationship("Workout", back_populates="stations")
    exercise = relationship("Exercise", back_populates="stations")
    sets = relationship(
        "SetEntry",
        back_populates="station",
        cascade="all, delete-orphan",
        order_by="SetEntry.set_number",
    )


class SetEntry(Base):
    __tablename__ = "set_entries"
    __table_args__ = (
        UniqueConstraint("station_id", "set_number", name="uq_set_station_number"),
        UniqueConstraint("user_id", "client_mutation_id", name="uq_set_user_mutation"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    station_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("workout_stations.id", ondelete="CASCADE"), index=True
    )
    set_number: Mapped[int] = mapped_column(Integer, nullable=False)
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    reps: Mapped[int] = mapped_column(Integer, nullable=False)
    rpe: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    client_mutation_id: Mapped[str | None] = mapped_column(String(120))
    station = relationship("WorkoutStation", back_populates="sets")
