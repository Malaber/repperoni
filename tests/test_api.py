import asyncio
import uuid

from app.api.deps import get_current_user, get_optional_current_user
from app.core.config import settings
from app.main import app
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


def test_health_and_auth_guards(client):
    app.dependency_overrides.clear()
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/").status_code == 200
    assert client.get("/api/v1/exercises").status_code == 401
    assert client.get("/apple-app-site-association").status_code == 404


def test_authenticated_web_shell_and_public_assets(client, user):
    app.dependency_overrides[get_optional_current_user] = lambda: user
    assert "Ready to get" in client.get("/").text
    assert client.get("/login", follow_redirects=False).headers["location"] == "/"
    assert client.get("/manifest.webmanifest").status_code == 200
    assert client.get("/service-worker.js").headers["cache-control"] == "no-cache"

    app.dependency_overrides[get_optional_current_user] = lambda: None
    assert 'data-next-url="/"' in client.get("/login?next=//evil.example").text
    settings.webcredentials_apps = ["TEAM.de.malaber.repperoni"]
    association = client.get("/.well-known/apple-app-site-association")
    assert association.json()["webcredentials"]["apps"] == ["TEAM.de.malaber.repperoni"]
    settings.webcredentials_apps = []


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
        json={"weight_kg": "80.50", "reps": 8, "client_mutation_id": mutation_id},
    )
    assert retried.status_code == 200
    assert retried.json()["id"] == first.json()["id"]

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
    entry = client.post(url, json={"weight_kg": 20, "reps": 10}).json()
    assert client.delete(f"{url}/{entry['id']}").status_code == 204
    assert client.delete(f"{url}/{entry['id']}").status_code == 404
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
    exercise = first_exercise(client)
    workout = start_workout(client)
    other = asyncio.run(create_user())
    app.dependency_overrides[get_current_user] = lambda: other
    assert client.get(f"/api/v1/workouts/{workout['id']}").status_code == 404
    assert (
        client.post(
            f"/api/v1/workouts/{workout['id']}/stations",
            json={"exercise_id": exercise["id"]},
        ).status_code
        == 404
    )
    app.dependency_overrides[get_current_user] = lambda: user


def test_validation_and_missing_resources(client):
    assert client.get("/api/v1/workouts/active").json() is None
    assert client.post("/api/v1/workouts", json={"name": ""}).status_code == 422
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
