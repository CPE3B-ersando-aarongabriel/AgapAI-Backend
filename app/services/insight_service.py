from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from app.core.settings import get_settings
from app.repositories.session_repository import SessionRepository
from app.schemas.insight_schema import InsightChatRequest, InsightChatResponse, InsightDataContext
from app.utils.helpers import utc_now


class InsightContextNotFoundError(Exception):
    pass


class InsightService:
    def __init__(self, repository: SessionRepository):
        self.repository = repository
        self.settings = get_settings()
        self._client: OpenAI | None = None
        if self.settings.openai_api_key:
            self._client = OpenAI(api_key=self.settings.openai_api_key)

    def ask(self, payload: InsightChatRequest) -> InsightChatResponse:
        context_bundle = self._build_context(payload)
        answer, ai_used = self._generate_answer(payload.question, context_bundle)
        generated_at = utc_now()

        if payload.store_conversation:
            session_for_history = context_bundle["context"].latest_session_id
            if session_for_history:
                self.repository.append_insight_history(
                    session_id=session_for_history,
                    entry={
                        "question": payload.question,
                        "answer": answer,
                        "generated_at": generated_at,
                        "mode": context_bundle["context"].mode,
                        "ai_used": ai_used,
                    },
                    now=generated_at,
                )

        return InsightChatResponse(
            question=payload.question,
            answer=answer,
            context=context_bundle["context"],
            ai_used=ai_used,
            grounded=True,
            generated_at=generated_at,
        )

    def _build_context(self, payload: InsightChatRequest) -> dict[str, Any]:
        target_session: dict[str, Any] | None = None

        mode: str = "generic"
        if payload.session_id:
            mode = "session"
            target_session = self.repository.get_session_by_id(payload.session_id)
            if not target_session:
                raise InsightContextNotFoundError(f"Session '{payload.session_id}' not found")
        elif payload.device_id:
            mode = "device"

        context_device_id = payload.device_id
        if target_session and not context_device_id:
            context_device_id = target_session.get("device_id")

        if not target_session:
            target_session = self.repository.get_latest_session(device_id=context_device_id)

        sessions, _ = self.repository.list_sessions(limit=5, skip=0, device_id=context_device_id)
        dashboard = self.repository.dashboard_aggregate(device_id=context_device_id)

        session_summary = self._summarize_session(target_session) if target_session else None

        context = InsightDataContext(
            mode=mode,
            device_id=context_device_id,
            session_id=payload.session_id,
            latest_session_id=(target_session or {}).get("session_id") if target_session else None,
            sessions_considered=len(sessions),
            has_pre_analysis=bool((target_session or {}).get("latest_pre_analysis")) if target_session else False,
            has_advanced_analysis=bool((target_session or {}).get("advanced_analysis")) if target_session else False,
            has_dashboard_context=True,
        )

        return {
            "context": context,
            "session_summary": session_summary,
            "recent_sessions": [self._summarize_session(item) for item in sessions],
            "dashboard": {
                "total_sessions": dashboard.get("total_sessions", 0),
                "average_breathing_rate": dashboard.get("average_breathing_rate", 0.0),
                "average_snore_level": dashboard.get("average_snore_level", 0.0),
                "latest_highlights": dashboard.get("latest", []),
                "trends": dashboard.get("trends", []),
            },
        }

    def _summarize_session(self, session_doc: dict[str, Any]) -> dict[str, Any]:
        events = list(session_doc.get("sensor_events") or [])
        latest_event = events[-1] if events else None

        avg_breathing = 0.0
        avg_snore = 0.0
        if events:
            avg_breathing = sum(float(e.get("breathing_rate") or 0.0) for e in events) / len(events)
            avg_snore = sum(float(e.get("snore_level") or 0.0) for e in events) / len(events)

        return {
            "session_id": session_doc.get("session_id"),
            "device_id": session_doc.get("device_id"),
            "started_at": session_doc.get("started_at"),
            "updated_at": session_doc.get("updated_at"),
            "event_count": len(events),
            "avg_breathing_rate": round(avg_breathing, 2),
            "avg_snore_level": round(avg_snore, 2),
            "latest_event": latest_event,
            "latest_pre_analysis": session_doc.get("latest_pre_analysis"),
            "latest_device_response": session_doc.get("latest_device_response"),
            "advanced_analysis": session_doc.get("advanced_analysis"),
        }

    def _generate_answer(self, question: str, context_bundle: dict[str, Any]) -> tuple[str, bool]:
        if not self._client:
            return self._fallback_answer(question, context_bundle), False

        prompt = (
            "You are AgapAI's sleep insight assistant. "
            "Answer only using backend-provided context data. "
            "If data is missing, explicitly state limits and avoid guessing. "
            "Provide practical, non-diagnostic sleep/breathing advice. "
            "Keep response concise and frontend-friendly. "
            f"User question: {question}\n"
            f"Data context JSON: {json.dumps(context_bundle, default=str)}"
        )

        try:
            response = self._client.responses.create(
                model=self.settings.openai_model,
                input=prompt,
                max_output_tokens=500,
            )
            text = (response.output_text or "").strip()
            if text:
                return text, True
        except Exception:
            pass

        return self._fallback_answer(question, context_bundle), False

    def _fallback_answer(self, question: str, context_bundle: dict[str, Any]) -> str:
        session_summary = context_bundle.get("session_summary") or {}
        dashboard = context_bundle.get("dashboard") or {}

        avg_br = float(session_summary.get("avg_breathing_rate") or dashboard.get("average_breathing_rate") or 0.0)
        avg_sn = float(session_summary.get("avg_snore_level") or dashboard.get("average_snore_level") or 0.0)
        event_count = int(session_summary.get("event_count") or 0)
        pre = session_summary.get("latest_pre_analysis") or {}

        lines = [
            f"Based on your stored AgapAI data, here is a grounded response to: '{question}'.",
            f"Recent context: {event_count} captured events, avg breathing {avg_br:.1f} bpm, avg snore {avg_sn:.1f}/100.",
        ]

        if pre:
            lines.append(f"Latest pre-analysis summary: {pre.get('summary', 'No summary available.')}")

        if avg_sn >= 60:
            lines.append("Action: prioritize side-sleep posture and reduce airway resistance before sleep.")
        elif avg_sn >= 30:
            lines.append("Action: keep posture stable and monitor snore trend for worsening nights.")
        else:
            lines.append("Action: current snore trend appears mild; maintain a consistent bedtime routine.")

        if avg_br > 18:
            lines.append("Action: use 4-1-5 breathing for 3-5 minutes pre-sleep to settle elevated breathing.")
        elif avg_br < 10:
            lines.append("Action: verify sensor placement; if values persist, continue tracking trend across sessions.")
        else:
            lines.append("Action: breathing trend is in a stable range; focus on room comfort and consistency.")

        lines.append("Note: This is a sleep coaching insight, not a medical diagnosis.")
        return "\n".join(lines)
