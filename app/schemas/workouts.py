from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


UTCDateTime = Annotated[datetime, AfterValidator(_ensure_utc)]


class ExerciseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    muscle_group: str = Field(min_length=1, max_length=80)
    equipment: str = Field(min_length=1, max_length=80)


class ExerciseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    muscle_group: str
    equipment: str
    is_custom: bool


class PerformanceOut(BaseModel):
    weight_kg: Decimal
    reps: int
    completed_at: UTCDateTime
    estimated_one_rep_max: Decimal


class SetCreate(BaseModel):
    weight_kg: Decimal = Field(ge=0, le=2000, decimal_places=2)
    reps: int = Field(ge=1, le=1000)
    rpe: Decimal | None = Field(default=None, ge=1, le=10, decimal_places=1)
    client_mutation_id: str | None = Field(default=None, min_length=1, max_length=120)


class SetUpdate(BaseModel):
    weight_kg: Decimal | None = Field(default=None, ge=0, le=2000, decimal_places=2)
    reps: int | None = Field(default=None, ge=1, le=1000)
    rpe: Decimal | None = Field(default=None, ge=1, le=10, decimal_places=1)

    @model_validator(mode="after")
    def require_change(self):
        if self.weight_kg is None and self.reps is None and self.rpe is None:
            raise ValueError("At least one set field is required")
        return self


class SetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    set_number: int
    weight_kg: Decimal
    reps: int
    rpe: Decimal | None
    completed_at: UTCDateTime
    client_mutation_id: str | None


class StationCreate(BaseModel):
    exercise_id: UUID


class StationOut(BaseModel):
    id: UUID
    position: int
    started_at: UTCDateTime
    exercise: ExerciseOut
    sets: list[SetOut]
    previous_performance: PerformanceOut | None


class WorkoutCreate(BaseModel):
    name: str = Field(default="Workout", min_length=1, max_length=120)
    notes: str | None = Field(default=None, max_length=2000)


class WorkoutOut(BaseModel):
    id: UUID
    name: str
    notes: str | None
    started_at: UTCDateTime
    completed_at: UTCDateTime | None
    stations: list[StationOut]
    total_sets: int
    total_volume_kg: Decimal


class WorkoutSummaryOut(BaseModel):
    id: UUID
    name: str
    started_at: UTCDateTime
    completed_at: UTCDateTime | None
    exercise_count: int
    total_sets: int
    total_volume_kg: Decimal


class VolumePoint(BaseModel):
    date: str
    volume_kg: Decimal


class PersonalRecordOut(BaseModel):
    exercise_id: UUID
    exercise_name: str
    weight_kg: Decimal
    reps: int
    estimated_one_rep_max: Decimal


class StatsOverviewOut(BaseModel):
    days: int
    workout_count: int
    total_sets: int
    total_volume_kg: Decimal
    current_streak: int
    volume_by_day: list[VolumePoint]
    personal_records: list[PersonalRecordOut]


class ProgressPoint(BaseModel):
    date: str
    best_weight_kg: Decimal
    best_estimated_one_rep_max: Decimal
    volume_kg: Decimal


class ExerciseProgressOut(BaseModel):
    exercise: ExerciseOut
    days: int
    points: list[ProgressPoint]
