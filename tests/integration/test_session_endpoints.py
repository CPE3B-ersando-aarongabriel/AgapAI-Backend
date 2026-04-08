from fastapi.testclient import TestClient
from pymongo.errors import OperationFailure

from app.dependencies.services import get_session_service
from app.exceptions.custom_exceptions import ServiceUnavailableError
from app.main import app


class FakeService:
    def start_session(self, payload):
        return {
            "session_id": "fake-001",
            "device_id": payload.device_id,
            "status": "started",
            "started_at": "2026-01-01T00:00:00Z",
        }


def test_root_supports_get_and_head():
    client = TestClient(app)

    get_response = client.get("/")
    assert get_response.status_code == 200
    assert get_response.json()["status"] == "ok"

    head_response = client.head("/")
    assert head_response.status_code == 200


def test_session_start_endpoint_with_dependency_override():
    app.dependency_overrides[get_session_service] = lambda: FakeService()
    client = TestClient(app)

    response = client.post(
        "/api/session/start",
        json={"device_id": "esp32-test", "metadata": {}},
    )

    assert response.status_code == 200
    assert response.json()["session_id"] == "fake-001"
    app.dependency_overrides.clear()


def test_session_start_returns_503_when_service_dependency_unavailable():
    def unavailable_service():
        raise ServiceUnavailableError("Database is unavailable")

    app.dependency_overrides[get_session_service] = unavailable_service
    client = TestClient(app)

    response = client.post(
        "/api/session/start",
        json={"device_id": "esp32-test", "metadata": {}},
    )

    assert response.status_code == 503
    payload = response.json()
    assert payload["error"] == "application_error"
    app.dependency_overrides.clear()


def test_session_start_returns_503_when_pymongo_failure_bubbles_up():
    def pymongo_failure_service():
        raise OperationFailure("bad auth", code=8000)

    app.dependency_overrides[get_session_service] = pymongo_failure_service
    client = TestClient(app)

    response = client.post(
        "/api/session/start",
        json={"device_id": "esp32-test", "metadata": {}},
    )

    assert response.status_code == 503
    payload = response.json()
    assert payload["error"] == "database_unavailable"
    app.dependency_overrides.clear()
