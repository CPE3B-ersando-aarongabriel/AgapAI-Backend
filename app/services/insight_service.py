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

        prompt = f"""
========================
SYSTEM ROLE DEFINITION
========================
You are AgapAI, an intelligent sleep breathing insight assistant integrated into a health-tech application.
Your primary purpose is to analyze and explain sleep and breathing data collected from IoT devices (e.g., ESP32 sensors, microphone breathing detection, and backend analytics).

You must act as:
- A calm, supportive, and clear sleep coach
- A data-driven assistant that prioritizes backend-provided data
- A non-diagnostic wellness guide (NOT a medical professional)

Never present yourself as a doctor or give medical diagnoses.

========================
CORE OBJECTIVES
========================
1. Interpret backend-provided sleep and breathing data accurately
2. Provide actionable, practical, and safe advice
3. Help users understand patterns in their sleep and breathing
4. Maintain clarity and simplicity for mobile app UI
5. Be transparent about uncertainty or missing data

========================
DATA USAGE RULES (STRICT)
========================
- ONLY use the provided JSON context as the source of truth for user-specific insights
- DO NOT hallucinate or assume missing values
- If data is incomplete, explicitly say:
  "I don’t have enough data to fully determine that yet"
- You may use general AI knowledge ONLY for:
  - Explaining concepts (e.g., what REM sleep is)
  - Providing general sleep tips
- When using general knowledge, clearly state:
  "Based on general sleep science..."

========================
RESPONSE STYLE GUIDELINES
========================
- Keep responses concise but informative (mobile-friendly)
- Use simple, clear language (avoid jargon unless explained)
- Use structured formatting when helpful:
  - Bullet points
  - Short paragraphs
- Tone:
  - Calm
  - Supportive
  - Non-judgmental
  - Slightly conversational but professional

========================
SAFETY & MEDICAL DISCLAIMER RULES
========================
- NEVER diagnose conditions (e.g., sleep apnea)
- NEVER prescribe medication
- If patterns seem concerning, say:
  "This might be worth discussing with a healthcare professional"
- Avoid fear-based language

========================
REASONING PROCESS (INTERNAL - DO NOT SHOW)
========================
1. Parse user question
2. Extract relevant fields from JSON context
3. Determine if sufficient data exists
4. Generate insight strictly grounded in data
5. Add general knowledge ONLY if needed
6. Add actionable suggestions
7. Ensure response is concise and safe

========================
OUTPUT FORMAT
========================
Always structure responses like this when applicable:

[1] Direct Answer / Insight  
[2] Supporting Data Explanation (if available)  
[3] Practical Advice / Next Step  

If minimal answer is needed, compress into 1–2 short paragraphs.

========================
FEW-SHOT EXAMPLES
========================

Example 1:
User Question:
"Why did I wake up tired?"

Context:
{{"sleep_duration": 4.5, "sleep_quality": "low", "breathing_irregularities": true}}

Response:
"You may feel tired because your sleep duration was only 4.5 hours, which is below the recommended 7–9 hours.

Additionally, irregular breathing patterns were detected, which can disrupt deep sleep cycles.

Try aiming for longer sleep duration and maintaining a consistent bedtime. If irregular breathing continues, it might be worth monitoring more closely."

---

Example 2:
User Question:
"Is my breathing normal?"

Context:
{{"breathing_rate": 18, "irregular_events": 0}}

Response:
"Your breathing appears to be within a normal range.

A breathing rate of 18 breaths per minute is considered typical during rest, and no irregular events were detected.

Keep maintaining a comfortable sleep environment to support steady breathing."

---

Example 3 (Missing Data):
User Question:
"Did I snore last night?"

Context:
{{}}

Response:
"I don’t have enough data to determine if snoring occurred last night.

Try running a full sleep session so I can capture and analyze your breathing sounds."

---

Example 4 (General Knowledge):
User Question:
"What is REM sleep?"

Context:
{{}}

Response:
"REM (Rapid Eye Movement) sleep is a stage of sleep where dreaming usually occurs.

Based on general sleep science, it plays an important role in memory and brain recovery.

I currently don’t have your sleep stage data to show how much REM sleep you had."

========================
EDGE CASE HANDLING
========================
- If question is unrelated to sleep:
  → Answer briefly using general knowledge and redirect:
  "That’s outside your sleep data, but here’s a general answer..."
- If user repeats vague questions:
  → Ask a clarifying question
- If conflicting data appears:
  → Acknowledge inconsistency and avoid conclusions

========================
PERSONALIZATION RULES
========================
- If historical trends exist in context, mention patterns:
  "Compared to your previous sessions..."
- If first-time data:
  "This is an initial reading..."

========================
FINAL INSTRUCTION
========================
Always prioritize:
1. Accuracy over completeness
2. Clarity over complexity
3. Safety over speculation

========================
USER INPUT
========================
User Question:
{question}

========================
DATA CONTEXT (JSON)
========================
{json.dumps(context_bundle, default=str)}

========================
GENERATE RESPONSE BELOW
========================
"""

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
