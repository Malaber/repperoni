import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from pydantic import SecretStr

from app.api.deps import get_current_user, get_optional_current_user
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import create_access_token
from app.main import app
from app.models import AuthSession
from tests.conftest import create_user


def first_exercise(client):
    response = client.get("/api/v1/exercises")
    assert response.status_code == 200
    assert len(response.json()) >= 12
    return response.json()[0]


def start_workout(client, name="Push day"):
    response = client.post("/api/v1/workouts", json={"name": name})
    assert response.status_code == 201
    return response.json()


def add_station(client, workout, exercise):
    response = client.post(
        f"/api/v1/workouts/{workout['id']}/stations",
        json={"exercise_id": exercise["id"]},
    )
    assert response.status_code == 201
    return response.json()


async def bearer_token_for(user):
    now = datetime.now(UTC)
    async with SessionLocal() as db:
        auth_session = AuthSession(
            user_id=user.id,
            last_seen_at=now,
            expires_at=now + timedelta(hours=1),
        )
        db.add(auth_session)
        await db.commit()
        await db.refresh(auth_session)
        return create_access_token(user.id, auth_session.id)


def test_health_and_auth_guards(client):
    app.dependency_overrides.clear()
    health = client.get("/health")
    assert health.json() == {"status": "ok"}
    assert client.get("/health/version").json() == {
        "status": "ok",
        "version": "dev",
        "revision": "unknown",
    }
    assert health.headers["x-content-type-options"] == "nosniff"
    assert health.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in health.headers["content-security-policy"]
    assert client.get("/health", headers={"Host": "evil.example"}).status_code == 400
    assert client.get("/").status_code == 200
    unauthorized = client.get("/api/v1/exercises")
    assert unauthorized.status_code == 401
    assert unauthorized.headers["cache-control"] == "private, no-store"
    assert client.get("/apple-app-site-association").status_code == 404


def test_authenticated_web_shell_and_public_assets(client, user):
    app.dependency_overrides[get_optional_current_user] = lambda: user
    assert "Ready to get" in client.get("/").text
    assert client.get("/login", follow_redirects=False).headers["location"] == "/"
    assert client.get("/manifest.webmanifest").status_code == 200
    assert client.get("/service-worker.js").headers["cache-control"] == "no-cache"

    app.dependency_overrides[get_optional_current_user] = lambda: None
    assert 'data-next-url="/"' in client.get("/login?next=//evil.example").text
    assert 'data-next-url="/"' in client.get("/login?next=%2F%5Cevil.example").text
    login = client.get("/login")
    assert '<script type="module" src=' in login.text
    assert login.headers["cache-control"] == "private, no-store"
    assert (
        "unsafe-inline"
        not in login.headers["content-security-policy"].split("script-src", 1)[1].split(";", 1)[0]
    )
    settings.webcredentials_apps = ["TEAM.de.malaber.repperoni"]
    association = client.get("/.well-known/apple-app-site-association")
    assert association.json()["webcredentials"]["apps"] == ["TEAM.de.malaber.repperoni"]
    settings.webcredentials_apps = []


def test_registration_ui_follows_bootstrap_policy(client, monkeypatch):
    app.dependency_overrides[get_optional_current_user] = lambda: None

    monkeypatch.setattr(settings, "registration_mode", "closed")
    assert 'data-testid="signup-tab"' not in client.get("/login").text

    monkeypatch.setattr(settings, "registration_mode", "first-user")
    monkeypatch.setattr(settings, "registration_bootstrap_token", SecretStr("b" * 32))
    login = client.get("/login")
    assert 'data-testid="signup-tab"' in login.text
    assert "data-registration-bootstrap-token" in login.text
    assert 'name="registration_bootstrap_token"' not in login.text
    assert '<form class="auth-form" method="post" action="/login"' in login.text


def test_request_origin_and_body_size_are_enforced(client, user):
    blocked = client.post("/logout", headers={"Origin": "https://evil.example"})
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == "Untrusted request origin"
    assert client.post("/logout", headers={"Origin": "null"}).status_code == 403

    same_origin = client.post(
        "/logout",
        headers={"Origin": "http://localhost"},
        follow_redirects=False,
    )
    assert same_origin.status_code == 303
    csrf_proved = client.post(
        "/logout",
        headers={"Origin": "null", "X-Repperoni-CSRF": "1"},
        follow_redirects=False,
    )
    assert csrf_proved.status_code == 303

    native = client.post(
        "/api/v1/workouts",
        json={"name": "Native workout"},
        headers={
            "Authorization": f"Bearer {asyncio.run(bearer_token_for(user))}",
            "Origin": "https://native.example",
        },
    )
    assert native.status_code == 201

    oversized = client.post(
        "/api/v1/workouts",
        content=b"x" * (settings.max_request_body_bytes + 1),
        headers={"Content-Type": "application/json"},
    )
    assert oversized.status_code == 413
    assert oversized.json()["detail"] == "Request body too large"


def test_exercise_catalog_search_and_custom_exercises(client):
    catalog = client.get("/api/v1/exercises").json()
    assert {item["name"] for item in catalog} >= {"Bench Press", "Squat", "Deadlift"}
    assert all(item["is_custom"] is False for item in catalog)

    search = client.get("/api/v1/exercises", params={"search": "bench"})
    assert [item["name"] for item in search.json()] == ["Bench Press"]

    payload = {"name": "Pepper Press", "muscle_group": "Core", "equipment": "Pizza"}
    created = client.post("/api/v1/exercises", json=payload)
    assert created.status_code == 201
    assert created.json()["is_custom"] is True
    assert client.post("/api/v1/exercises", json=payload).status_code == 409


def test_complete_workout_and_previous_performance(client):
    exercise = first_exercise(client)
    workout = start_workout(client)
    assert workout["started_at"].endswith("Z")
    assert client.post("/api/v1/workouts", json={"name": "Duplicate"}).status_code == 409
    workout = add_station(client, workout, exercise)
    station = workout["stations"][0]
    assert station["previous_performance"] is None
    duplicate = client.post(
        f"/api/v1/workouts/{workout['id']}/stations",
        json={"exercise_id": exercise["id"]},
    )
    assert duplicate.status_code == 409

    set_url = f"/api/v1/workouts/{workout['id']}/stations/{station['id']}/sets"
    mutation_id = str(uuid.uuid4())
    first = client.post(
        set_url,
        json={"weight_kg": "80.50", "reps": 8, "rpe": "8.5", "client_mutation_id": mutation_id},
    )
    assert first.status_code == 201
    assert first.json()["set_number"] == 1
    assert first.json()["completed_at"].endswith("Z")
    retried = client.post(
        set_url,
        json={
            "weight_kg": "80.50",
            "reps": 8,
            "rpe": "8.5",
            "client_mutation_id": mutation_id,
        },
    )
    assert retried.status_code == 200
    assert retried.json()["id"] == first.json()["id"]
    conflicting_retry = client.post(
        set_url,
        json={"weight_kg": "81", "reps": 8, "client_mutation_id": mutation_id},
    )
    assert conflicting_retry.status_code == 409

    changed = client.patch(
        f"{set_url}/{first.json()['id']}", json={"weight_kg": "82.50", "reps": 7}
    )
    assert changed.status_code == 200
    assert changed.json()["weight_kg"] == "82.50"
    assert client.patch(f"{set_url}/{first.json()['id']}", json={}).status_code == 422

    last = client.get(f"/api/v1/exercises/{exercise['id']}/last-performance")
    assert last.json()["weight_kg"] == "82.50"
    assert last.json()["estimated_one_rep_max"] == "101.75"

    finished = client.post(f"/api/v1/workouts/{workout['id']}/finish")
    assert finished.status_code == 200
    assert finished.json()["total_volume_kg"] == "577.50"
    assert finished.json()["completed_at"].endswith("Z")
    assert client.post(f"/api/v1/workouts/{workout['id']}/finish").status_code == 409

    next_workout = add_station(client, start_workout(client, "Round two"), exercise)
    previous = next_workout["stations"][0]["previous_performance"]
    assert previous["weight_kg"] == "82.50"
    assert previous["reps"] == 7


def test_set_delete_and_workout_listing(client):
    exercise = first_exercise(client)
    workout = add_station(client, start_workout(client), exercise)
    station = workout["stations"][0]
    url = f"/api/v1/workouts/{workout['id']}/stations/{station['id']}/sets"
    first = client.post(url, json={"weight_kg": 20, "reps": 10}).json()
    second = client.post(url, json={"weight_kg": 21, "reps": 9}).json()
    assert client.delete(f"{url}/{first['id']}").status_code == 204
    assert client.delete(f"{url}/{first['id']}").status_code == 404
    after_gap = client.post(url, json={"weight_kg": 22, "reps": 8})
    assert after_gap.status_code == 201
    assert after_gap.json()["set_number"] == 3
    assert client.delete(f"{url}/{second['id']}").status_code == 204
    assert client.delete(f"{url}/{after_gap.json()['id']}").status_code == 204
    assert client.get(f"/api/v1/workouts/{workout['id']}").json()["total_sets"] == 0
    assert client.get("/api/v1/workouts", params={"limit": 1}).status_code == 200


def test_statistics_and_exercise_progress(client):
    exercise = first_exercise(client)
    workout = add_station(client, start_workout(client), exercise)
    station = workout["stations"][0]
    url = f"/api/v1/workouts/{workout['id']}/stations/{station['id']}/sets"
    client.post(url, json={"weight_kg": 100, "reps": 5})
    client.post(url, json={"weight_kg": 90, "reps": 8})
    client.post(f"/api/v1/workouts/{workout['id']}/finish")

    overview = client.get("/api/v1/stats/overview", params={"days": 90})
    assert overview.status_code == 200
    data = overview.json()
    assert data["workout_count"] >= 1
    assert data["total_sets"] >= 2
    assert data["personal_records"][0]["exercise_id"] == exercise["id"]

    progress = client.get(f"/api/v1/stats/exercises/{exercise['id']}/progress")
    assert progress.status_code == 200
    assert progress.json()["points"][-1]["volume_kg"] == "1220.00"


def test_cross_user_resources_are_hidden(client, user):
    custom = client.post(
        "/api/v1/exercises",
        json={"name": "Private Press", "muscle_group": "Core", "equipment": "Pizza"},
    ).json()
    workout = add_station(client, start_workout(client), custom)
    station = workout["stations"][0]
    set_url = f"/api/v1/workouts/{workout['id']}/stations/{station['id']}/sets"
    entry = client.post(set_url, json={"weight_kg": 42, "reps": 6}).json()

    other = asyncio.run(create_user())
    app.dependency_overrides[get_current_user] = lambda: other
    assert client.get(f"/api/v1/workouts/{workout['id']}").status_code == 404
    assert all(item["id"] != workout["id"] for item in client.get("/api/v1/workouts").json())
    assert client.get("/api/v1/workouts/active").json() is None
    assert all(item["id"] != custom["id"] for item in client.get("/api/v1/exercises").json())
    assert client.get(f"/api/v1/exercises/{custom['id']}/last-performance").status_code == 404
    assert client.get(f"/api/v1/stats/exercises/{custom['id']}/progress").status_code == 404
    overview = client.get("/api/v1/stats/overview").json()
    assert overview["workout_count"] == 0
    assert overview["total_sets"] == 0
    assert (
        client.post(
            f"/api/v1/workouts/{workout['id']}/stations",
            json={"exercise_id": custom["id"]},
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"{set_url}/{entry['id']}",
            json={"weight_kg": 1},
        ).status_code
        == 404
    )
    assert client.delete(f"{set_url}/{entry['id']}").status_code == 404

    app.dependency_overrides[get_current_user] = lambda: user
    assert client.get(f"/api/v1/workouts/{workout['id']}").json()["total_sets"] == 1


def test_validation_and_missing_resources(client):
    assert client.get("/api/v1/workouts/active").json() is None
    assert client.post("/api/v1/workouts", json={"name": ""}).status_code == 422
    assert client.post("/api/v1/workouts", json={"name": "   "}).status_code == 422
    for field in ("name", "muscle_group", "equipment"):
        exercise = {"name": "Press", "muscle_group": "Chest", "equipment": "Barbell"}
        exercise[field] = " \n "
        assert client.post("/api/v1/exercises", json=exercise).status_code == 422
    assert client.get(f"/api/v1/workouts/{uuid.uuid4()}").status_code == 404
    assert client.get(f"/api/v1/exercises/{uuid.uuid4()}/last-performance").status_code == 404
    workout = start_workout(client)
    assert (
        client.post(
            f"/api/v1/workouts/{workout['id']}/stations/{uuid.uuid4()}/sets",
            json={"weight_kg": 20, "reps": 8},
        ).status_code
        == 404
    )
    empty_stats = client.get("/api/v1/stats/overview")
    assert empty_stats.json()["current_streak"] == 0
