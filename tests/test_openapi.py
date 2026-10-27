from app.api.deps import get_current_user
from app.main import app
from app.schemas import ErrorOut


def test_openapi_describes_jwt_bearer_authentication():
    schema = app.openapi()

    assert schema["components"]["securitySchemes"] == {
        "BearerAuth": {
            "type": "http",
            "description": "JWT access token returned by passkey login verification.",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
    }
    assert schema["paths"]["/api/v1/workouts"]["get"]["security"] == [{"BearerAuth": []}]
    assert schema["paths"]["/api/v1/workouts"]["post"]["security"] == [{"BearerAuth": []}]


def test_api_authentication_challenges_with_bearer(client):
    app.dependency_overrides.pop(get_current_user, None)

    missing = client.get("/api/v1/exercises")
    assert missing.status_code == 401
    assert missing.headers["www-authenticate"] == "Bearer"
    assert missing.json() == ErrorOut(detail="Authentication required").model_dump()

    invalid = client.get(
        "/api/v1/exercises",
        headers={"Authorization": "Bearer invalid"},
    )
    assert invalid.status_code == 401
    assert invalid.headers["www-authenticate"] == "Bearer"
    assert invalid.json() == ErrorOut(detail="Authentication required").model_dump()
