from fastapi.testclient import TestClient

from app.dependencies.services import get_insight_service
from app.main import app


class FakeInsightService:
    def ask(self, payload):
        return {
            "question": payload.question,
            "answer": "Grounded response from stored data.",
            "context": {
                "mode": "session",
                "device_id": "esp32-test",
                "session_id": payload.session_id,
                "latest_session_id": payload.session_id,
                "sessions_considered": 3,
                "has_pre_analysis": True,
                "has_advanced_analysis": False,
                "has_dashboard_context": True,
            },
            "ai_used": False,
            "grounded": True,
            "generated_at": "2026-04-07T00:00:00Z",
        }


def test_insight_chat_endpoint_with_dependency_override():
    app.dependency_overrides[get_insight_service] = lambda: FakeInsightService()
    client = TestClient(app)

    response = client.post(
        "/api/insight/chat",
        json={
            "question": "How can I improve tonight's sleep?",
            "session_id": "esp32-20260407000000-abcd1234",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["grounded"] is True
    assert payload["context"]["mode"] == "session"

    app.dependency_overrides.clear()
