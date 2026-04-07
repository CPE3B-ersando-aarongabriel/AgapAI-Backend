from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.insight_schema import InsightChatRequest
from app.services.insight_service import InsightContextNotFoundError, InsightService


NOW = datetime(2026, 4, 7, tzinfo=timezone.utc)


class FakeRepo:
    def __init__(self):
        self.sessions = {
            "sess-001": {
                "session_id": "sess-001",
                "device_id": "esp32-a",
                "started_at": NOW,
                "updated_at": NOW,
                "sensor_events": [
                    {"breathing_rate": 14.0, "snore_level": 28.0, "temperature": 26.0, "humidity": 58.0},
                    {"breathing_rate": 15.0, "snore_level": 32.0, "temperature": 26.5, "humidity": 59.0},
                ],
                "latest_pre_analysis": {"summary": "Mild snore with stable breathing."},
                "latest_device_response": {"recommendations": ["Keep side posture", "Maintain cool room", "Nasal breathing"]},
                "advanced_analysis": {"detailed_insights": ["Trend mildly elevated snore"]},
                "insight_history": [],
            }
        }

    def get_session_by_id(self, session_id: str):
        return self.sessions.get(session_id)

    def get_latest_session(self, device_id: str | None = None):
        for session in self.sessions.values():
            if device_id is None or session["device_id"] == device_id:
                return session
        return None

    def list_sessions(self, limit: int, skip: int, device_id: str | None = None):
        items = list(self.sessions.values())
        if device_id:
            items = [item for item in items if item["device_id"] == device_id]
        return items[skip : skip + limit], len(items)

    def dashboard_aggregate(self, device_id: str | None = None):
        return {
            "total_sessions": 1,
            "average_breathing_rate": 14.5,
            "average_snore_level": 30.0,
            "latest": list(self.sessions.values()),
            "trends": [],
        }

    def append_insight_history(self, session_id: str, entry: dict, now: datetime):
        self.sessions[session_id]["insight_history"].append(entry)
        self.sessions[session_id]["updated_at"] = now
        return self.sessions[session_id]


def test_insight_service_session_scoped_fallback_answer() -> None:
    service = InsightService(repository=FakeRepo())

    response = service.ask(
        InsightChatRequest(
            question="How can I reduce snoring tonight?",
            session_id="sess-001",
        )
    )

    assert response.context.mode == "session"
    assert response.context.latest_session_id == "sess-001"
    assert response.grounded is True
    assert "snor" in response.answer.lower()


def test_insight_service_stores_history_when_requested() -> None:
    repo = FakeRepo()
    service = InsightService(repository=repo)

    _ = service.ask(
        InsightChatRequest(
            question="Give me sleep advice from my latest data",
            session_id="sess-001",
            store_conversation=True,
        )
    )

    assert len(repo.sessions["sess-001"]["insight_history"]) == 1


def test_insight_service_raises_for_unknown_session() -> None:
    service = InsightService(repository=FakeRepo())

    try:
        service.ask(InsightChatRequest(question="test", session_id="missing-session"))
        raise AssertionError("Expected InsightContextNotFoundError")
    except InsightContextNotFoundError:
        assert True
