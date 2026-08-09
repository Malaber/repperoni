from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import Exercise, SetEntry, User, Workout, WorkoutStation
from app.schemas.workouts import (
    ExerciseCreate,
    ExerciseOut,
    ExerciseProgressOut,
    PerformanceOut,
    PersonalRecordOut,
    ProgressPoint,
    SetCreate,
    SetOut,
    SetUpdate,
    StationCreate,
    StatsOverviewOut,
    VolumePoint,
    WorkoutCreate,
    WorkoutOut,
    WorkoutSummaryOut,
)

router = APIRouter(tags=["workouts"])
ZERO = Decimal("0.00")


def _money(value: Decimal | int | float) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _one_rep_max(weight: Decimal, reps: int) -> Decimal:
    return _money(weight * (Decimal(1) + Decimal(reps) / Decimal(30)))


def _exercise_out(exercise: Exercise) -> ExerciseOut:
    return ExerciseOut(
        id=exercise.id,
        name=exercise.name,
        muscle_group=exercise.muscle_group,
        equipment=exercise.equipment,
        is_custom=exercise.user_id is not None,
    )


def _set_out(entry: SetEntry) -> SetOut:
    return SetOut.model_validate(entry)


def _idempotent_set_out(
    entry: SetEntry,
    station_id: UUID,
    payload: SetCreate,
    response: Response,
) -> SetOut:
    if (
        entry.station_id != station_id
        or entry.weight_kg != payload.weight_kg
        or entry.reps != payload.reps
        or entry.rpe != payload.rpe
    ):
        raise HTTPException(
            status_code=409,
            detail="Client mutation ID was already used for another set",
        )
    response.status_code = status.HTTP_200_OK
    return _set_out(entry)


async def _exercise_for_user(db: AsyncSession, exercise_id: UUID, user_id: UUID) -> Exercise:
    result = await db.execute(
        select(Exercise).where(
            Exercise.id == exercise_id, or_(Exercise.user_id.is_(None), Exercise.user_id == user_id)
        )
    )
    exercise = result.scalar_one_or_none()
    if exercise is None:
        raise HTTPException(status_code=404, detail="Exercise not found")
    return exercise


def _workout_query(workout_id: UUID | None = None):
    query = (
        select(Workout)
        .options(
            selectinload(Workout.stations).selectinload(WorkoutStation.exercise),
            selectinload(Workout.stations).selectinload(WorkoutStation.sets),
        )
        .execution_options(populate_existing=True)
    )
    return query if workout_id is None else query.where(Workout.id == workout_id)


async def _workout_for_user(db: AsyncSession, workout_id: UUID, user_id: UUID) -> Workout:
    result = await db.execute(_workout_query(workout_id).where(Workout.user_id == user_id))
    workout = result.scalar_one_or_none()
    if workout is None:
        raise HTTPException(status_code=404, detail="Workout not found")
    return workout


async def _previous_performance(
    db: AsyncSession, exercise_id: UUID, user_id: UUID, exclude_workout_id: UUID | None = None
) -> PerformanceOut | None:
    query = (
        select(SetEntry)
        .join(WorkoutStation)
        .join(Workout)
        .where(SetEntry.user_id == user_id, WorkoutStation.exercise_id == exercise_id)
    )
    if exclude_workout_id is not None:
        query = query.where(Workout.id != exclude_workout_id)
    result = await db.execute(query.order_by(SetEntry.completed_at.desc()).limit(1))
    entry = result.scalar_one_or_none()
    if entry is None:
        return None
    return PerformanceOut(
        weight_kg=entry.weight_kg,
        reps=entry.reps,
        completed_at=entry.completed_at,
        estimated_one_rep_max=_one_rep_max(entry.weight_kg, entry.reps),
    )


async def _workout_out(db: AsyncSession, workout: Workout) -> WorkoutOut:
    stations = []
    volume = ZERO
    total_sets = 0
    for station in workout.stations:
        station_sets = [_set_out(entry) for entry in station.sets]
        total_sets += len(station.sets)
        volume += sum((entry.weight_kg * entry.reps for entry in station.sets), ZERO)
        stations.append(
            {
                "id": station.id,
                "position": station.position,
                "started_at": station.started_at,
                "exercise": _exercise_out(station.exercise),
                "sets": station_sets,
                "previous_performance": await _previous_performance(
                    db, station.exercise_id, workout.user_id, workout.id
                ),
            }
        )
    return WorkoutOut(
        id=workout.id,
        name=workout.name,
        notes=workout.notes,
        started_at=workout.started_at,
        completed_at=workout.completed_at,
        stations=stations,
        total_sets=total_sets,
        total_volume_kg=_money(volume),
    )


def _require_active(workout: Workout) -> None:
    if workout.completed_at is not None:
        raise HTTPException(status_code=409, detail="Workout is already finished")


@router.get("/exercises", response_model=list[ExerciseOut])
async def list_exercises(
    search: str = Query(default="", max_length=120),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(Exercise).where(or_(Exercise.user_id.is_(None), Exercise.user_id == user.id))
    if search.strip():
        query = query.where(func.lower(Exercise.name).contains(search.strip().lower()))
    result = await db.execute(query.order_by(Exercise.name))
    return [_exercise_out(item) for item in result.scalars()]


@router.post("/exercises", response_model=ExerciseOut, status_code=201)
async def create_exercise(
    payload: ExerciseCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    existing = await db.execute(
        select(Exercise).where(
            Exercise.user_id == user.id, func.lower(Exercise.name) == payload.name.strip().lower()
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="You already have an exercise with that name")
    exercise = Exercise(
        user_id=user.id,
        name=payload.name.strip(),
        muscle_group=payload.muscle_group.strip(),
        equipment=payload.equipment.strip(),
    )
    db.add(exercise)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="You already have an exercise with that name",
        ) from exc
    await db.refresh(exercise)
    return _exercise_out(exercise)


@router.get("/exercises/{exercise_id}/last-performance", response_model=PerformanceOut | None)
async def last_performance(
    exercise_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    await _exercise_for_user(db, exercise_id, user.id)
    return await _previous_performance(db, exercise_id, user.id)


@router.get("/workouts", response_model=list[WorkoutSummaryOut])
async def list_workouts(
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        _workout_query()
        .where(Workout.user_id == user.id)
        .order_by(Workout.started_at.desc())
        .limit(limit)
    )
    summaries = []
    for workout in result.scalars().unique():
        entries = [entry for station in workout.stations for entry in station.sets]
        summaries.append(
            WorkoutSummaryOut(
                id=workout.id,
                name=workout.name,
                started_at=workout.started_at,
                completed_at=workout.completed_at,
                exercise_count=len(workout.stations),
                total_sets=len(entries),
                total_volume_kg=_money(
                    sum((entry.weight_kg * entry.reps for entry in entries), ZERO)
                ),
            )
        )
    return summaries


@router.get("/workouts/active", response_model=WorkoutOut | None)
async def active_workout(
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    result = await db.execute(
        _workout_query()
        .where(Workout.user_id == user.id, Workout.completed_at.is_(None))
        .order_by(Workout.started_at.desc())
        .limit(1)
    )
    workout = result.scalar_one_or_none()
    return None if workout is None else await _workout_out(db, workout)


@router.post("/workouts", response_model=WorkoutOut, status_code=201)
async def create_workout(
    payload: WorkoutCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    active = await db.execute(
        select(Workout.id).where(Workout.user_id == user.id, Workout.completed_at.is_(None))
    )
    if active.first():
        raise HTTPException(status_code=409, detail="Finish your active workout first")
    workout = Workout(
        user_id=user.id,
        name=payload.name.strip(),
        notes=payload.notes,
        started_at=datetime.now(UTC),
    )
    db.add(workout)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Finish your active workout first") from exc
    return await _workout_out(db, await _workout_for_user(db, workout.id, user.id))


@router.get("/workouts/{workout_id}", response_model=WorkoutOut)
async def get_workout(
    workout_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await _workout_out(db, await _workout_for_user(db, workout_id, user.id))


@router.post("/workouts/{workout_id}/finish", response_model=WorkoutOut)
async def finish_workout(
    workout_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    workout = await _workout_for_user(db, workout_id, user.id)
    _require_active(workout)
    workout.completed_at = datetime.now(UTC)
    await db.commit()
    return await _workout_out(db, await _workout_for_user(db, workout.id, user.id))


@router.post("/workouts/{workout_id}/stations", response_model=WorkoutOut, status_code=201)
async def add_station(
    workout_id: UUID,
    payload: StationCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    workout = await _workout_for_user(db, workout_id, user.id)
    _require_active(workout)
    await _exercise_for_user(db, payload.exercise_id, user.id)
    if any(station.exercise_id == payload.exercise_id for station in workout.stations):
        raise HTTPException(status_code=409, detail="That station is already in this workout")
    for _ in range(3):
        position = await db.scalar(
            select(func.coalesce(func.max(WorkoutStation.position), 0) + 1).where(
                WorkoutStation.workout_id == workout.id
            )
        )
        station = WorkoutStation(
            workout_id=workout.id,
            exercise_id=payload.exercise_id,
            position=position,
            started_at=datetime.now(UTC),
        )
        db.add(station)
        try:
            await db.commit()
            break
        except IntegrityError:
            await db.rollback()
            existing = await db.scalar(
                select(WorkoutStation.id).where(
                    WorkoutStation.workout_id == workout.id,
                    WorkoutStation.exercise_id == payload.exercise_id,
                )
            )
            if existing is not None:
                raise HTTPException(
                    status_code=409,
                    detail="That station is already in this workout",
                )
    else:
        raise HTTPException(status_code=409, detail="A station was added concurrently; retry")
    return await _workout_out(db, await _workout_for_user(db, workout.id, user.id))


async def _station(workout: Workout, station_id: UUID) -> WorkoutStation:
    station = next((item for item in workout.stations if item.id == station_id), None)
    if station is None:
        raise HTTPException(status_code=404, detail="Station not found")
    return station


@router.post(
    "/workouts/{workout_id}/stations/{station_id}/sets", response_model=SetOut, status_code=201
)
async def add_set(
    workout_id: UUID,
    station_id: UUID,
    payload: SetCreate,
    response: Response,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    workout = await _workout_for_user(db, workout_id, user.id)
    _require_active(workout)
    station = await _station(workout, station_id)
    if payload.client_mutation_id:
        existing = await db.execute(
            select(SetEntry).where(
                SetEntry.user_id == user.id,
                SetEntry.client_mutation_id == payload.client_mutation_id,
            )
        )
        if entry := existing.scalar_one_or_none():
            return _idempotent_set_out(entry, station.id, payload, response)
    for _ in range(3):
        set_number = await db.scalar(
            select(func.coalesce(func.max(SetEntry.set_number), 0) + 1).where(
                SetEntry.station_id == station.id
            )
        )
        entry = SetEntry(
            user_id=user.id,
            station_id=station.id,
            set_number=set_number,
            weight_kg=payload.weight_kg,
            reps=payload.reps,
            rpe=payload.rpe,
            completed_at=datetime.now(UTC),
            client_mutation_id=payload.client_mutation_id,
        )
        db.add(entry)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            if payload.client_mutation_id:
                existing = await db.scalar(
                    select(SetEntry).where(
                        SetEntry.user_id == user.id,
                        SetEntry.client_mutation_id == payload.client_mutation_id,
                    )
                )
                if existing is not None:
                    return _idempotent_set_out(existing, station.id, payload, response)
            continue
        await db.refresh(entry)
        return _set_out(entry)
    raise HTTPException(status_code=409, detail="A set was added concurrently; retry")


async def _set_for_user(
    db: AsyncSession, set_id: UUID, station_id: UUID, user_id: UUID
) -> SetEntry:
    result = await db.execute(
        select(SetEntry).where(
            SetEntry.id == set_id, SetEntry.station_id == station_id, SetEntry.user_id == user_id
        )
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=404, detail="Set not found")
    return entry


@router.patch("/workouts/{workout_id}/stations/{station_id}/sets/{set_id}", response_model=SetOut)
async def update_set(
    workout_id: UUID,
    station_id: UUID,
    set_id: UUID,
    payload: SetUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    workout = await _workout_for_user(db, workout_id, user.id)
    _require_active(workout)
    await _station(workout, station_id)
    entry = await _set_for_user(db, set_id, station_id, user.id)
    changes = payload.model_dump(exclude_unset=True)
    for name, value in changes.items():
        setattr(entry, name, value)
    await db.commit()
    await db.refresh(entry)
    return _set_out(entry)


@router.delete("/workouts/{workout_id}/stations/{station_id}/sets/{set_id}", status_code=204)
async def delete_set(
    workout_id: UUID,
    station_id: UUID,
    set_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    workout = await _workout_for_user(db, workout_id, user.id)
    _require_active(workout)
    await _station(workout, station_id)
    entry = await _set_for_user(db, set_id, station_id, user.id)
    await db.delete(entry)
    await db.commit()


async def _history_rows(
    db: AsyncSession, user_id: UUID, since: datetime, exercise_id: UUID | None = None
):
    query = (
        select(SetEntry, WorkoutStation, Workout, Exercise)
        .join(WorkoutStation, SetEntry.station_id == WorkoutStation.id)
        .join(Workout, WorkoutStation.workout_id == Workout.id)
        .join(Exercise, WorkoutStation.exercise_id == Exercise.id)
        .where(SetEntry.user_id == user_id, SetEntry.completed_at >= since)
    )
    if exercise_id:
        query = query.where(Exercise.id == exercise_id)
    return (await db.execute(query.order_by(SetEntry.completed_at))).all()


@router.get("/stats/overview", response_model=StatsOverviewOut)
async def stats_overview(
    days: int = Query(default=90, ge=7, le=730),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    since = datetime.now(UTC) - timedelta(days=days)
    rows = await _history_rows(db, user.id, since)
    completed = await db.execute(
        select(Workout)
        .where(
            Workout.user_id == user.id,
            Workout.completed_at.is_not(None),
            Workout.completed_at >= since,
        )
        .order_by(Workout.completed_at.desc())
    )
    workouts = list(completed.scalars())
    volumes: dict[str, Decimal] = defaultdict(lambda: ZERO)
    records = {}
    total = ZERO
    for entry, station, _, exercise in rows:
        volume = entry.weight_kg * entry.reps
        total += volume
        volumes[entry.completed_at.date().isoformat()] += volume
        estimate = _one_rep_max(entry.weight_kg, entry.reps)
        current = records.get(exercise.id)
        if current is None or estimate > current.estimated_one_rep_max:
            records[exercise.id] = PersonalRecordOut(
                exercise_id=exercise.id,
                exercise_name=exercise.name,
                weight_kg=entry.weight_kg,
                reps=entry.reps,
                estimated_one_rep_max=estimate,
            )
    workout_dates = {item.completed_at.date() for item in workouts if item.completed_at}
    streak = 0
    cursor = date.today()
    if cursor not in workout_dates:
        cursor -= timedelta(days=1)
    while cursor in workout_dates:
        streak += 1
        cursor -= timedelta(days=1)
    return StatsOverviewOut(
        days=days,
        workout_count=len(workouts),
        total_sets=len(rows),
        total_volume_kg=_money(total),
        current_streak=streak,
        volume_by_day=[
            VolumePoint(date=day, volume_kg=_money(value)) for day, value in sorted(volumes.items())
        ],
        personal_records=sorted(
            records.values(), key=lambda item: item.estimated_one_rep_max, reverse=True
        )[:8],
    )


@router.get("/stats/exercises/{exercise_id}/progress", response_model=ExerciseProgressOut)
async def exercise_progress(
    exercise_id: UUID,
    days: int = Query(default=365, ge=7, le=1825),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    exercise = await _exercise_for_user(db, exercise_id, user.id)
    rows = await _history_rows(db, user.id, datetime.now(UTC) - timedelta(days=days), exercise_id)
    daily = {}
    for entry, *_ in rows:
        key = entry.completed_at.date().isoformat()
        point = daily.setdefault(key, {"weight": ZERO, "estimate": ZERO, "volume": ZERO})
        point["weight"] = max(point["weight"], entry.weight_kg)
        point["estimate"] = max(point["estimate"], _one_rep_max(entry.weight_kg, entry.reps))
        point["volume"] += entry.weight_kg * entry.reps
    points = [
        ProgressPoint(
            date=day,
            best_weight_kg=_money(values["weight"]),
            best_estimated_one_rep_max=_money(values["estimate"]),
            volume_kg=_money(values["volume"]),
        )
        for day, values in sorted(daily.items())
    ]
    return ExerciseProgressOut(exercise=_exercise_out(exercise), days=days, points=points)
