from fastapi.testclient import TestClient

from app.dependencies.services import get_session_service
from app.main import app


class FakeService:
    def start_session(self, payload):
        return {
            "session_id": "fake-001",
            "device_id": payload.device_id,
            "status": "started",
            "started_at": "2026-01-01T00:00:00Z",
        }


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
