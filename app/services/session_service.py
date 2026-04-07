from __future__ import annotations

from typing import Any

from app.models.session_model import build_session_document
from app.repositories.session_repository import SessionRepository
from app.schemas.session_schema import (
    AdvancedAnalysisRequest,
    AdvancedAnalysisResponse,
    AudioSummaryIn,
    CaptureWindowSummary,
    DashboardLatestHighlight,
    DashboardResponse,
    DashboardTrendPoint,
    DeviceDataResponse,
    RuleBasedSummary,
    SensorDataIn,
    SessionHistoryResponse,
    SessionListQuery,
    SessionRecordResponse,
    SessionStartRequest,
    SessionStartResponse,
)
from app.services.analysis_service import AnalysisService
from app.services.capture_service import aggregate_capture_samples
from app.utils.helpers import build_event_id, generate_session_id, normalize_sensor_payload, utc_now


class SessionNotFoundError(Exception):
    pass


class SessionService:
    def __init__(self, repository: SessionRepository, analysis_service: AnalysisService):
        self.repository = repository
        self.analysis_service = analysis_service

    def start_session(self, payload: SessionStartRequest) -> SessionStartResponse:
        now = utc_now()
        session_id = generate_session_id(payload.device_id)
        document = build_session_document(
            session_id=session_id,
            device_id=payload.device_id,
            firmware_version=payload.firmware_version,
            metadata=payload.metadata,
            now=now,
        )
        stored = self.repository.create_session(document)
        return SessionStartResponse(
            session_id=stored["session_id"],
            device_id=stored["device_id"],
            status="started",
            started_at=stored["started_at"],
        )

    def ingest_sensor_data(self, payload: SensorDataIn) -> DeviceDataResponse:
        session = self.repository.get_session_by_id(payload.session_id)
        if not session:
            raise SessionNotFoundError(f"Session '{payload.session_id}' not found")

        now = utc_now()
        payload_dict = payload.model_dump()

        capture_window_summary: dict[str, Any] | None = None
        audio_summary: dict[str, Any] | None = payload_dict.get("audio_summary")
        capture_samples = payload_dict.get("capture_samples") or []
        if capture_samples:
            aggregation = aggregate_capture_samples(capture_samples)
            capture_window_summary = aggregation.window_summary
            audio_summary = aggregation.audio_summary

            payload_dict["capture_samples"] = aggregation.normalized_samples
            payload_dict["capture_window_summary"] = capture_window_summary
            payload_dict["audio_summary"] = audio_summary

            for key in ("breathing_rate", "snore_level", "temperature", "humidity", "movement_level", "presence_detected"):
                if payload_dict.get(key) is None:
                    payload_dict[key] = aggregation.summarized_values.get(key)

            payload_dict["avg_mic_raw"] = aggregation.summarized_values["avg_mic_raw"]
            payload_dict["max_mic_raw"] = aggregation.summarized_values["max_mic_raw"]
            payload_dict["sample_count"] = aggregation.summarized_values["sample_count"]

            if payload_dict.get("mic_raw") is None:
                payload_dict["mic_raw"] = aggregation.summarized_values["avg_mic_raw"]

        if payload_dict.get("snore_level") is None and audio_summary is not None:
            payload_dict["snore_level"] = audio_summary.get("snore_score")

        if capture_window_summary is not None and payload_dict.get("recorded_at") is None:
            payload_dict["recorded_at"] = capture_window_summary["window_ended_at"]

        payload_dict = normalize_sensor_payload(payload_dict)
        if payload_dict.get("recorded_at") is None:
            payload_dict["recorded_at"] = now

        analysis_payload = {
            "breathing_rate": payload_dict["breathing_rate"],
            "snore_level": payload_dict["snore_level"],
            "temperature": payload_dict["temperature"],
            "humidity": payload_dict["humidity"],
            "movement_level": payload_dict.get("movement_level"),
            "presence_detected": payload_dict.get("presence_detected"),
            "mic_raw": payload_dict.get("mic_raw"),
            "audio_summary": audio_summary,
            "recorded_at": payload_dict["recorded_at"],
        }

        payload_dict["event_id"] = build_event_id(payload.session_id, payload_dict)

        pre_analysis = self.analysis_service.pre_analyze(analysis_payload)
        breathing_pattern = self.analysis_service.build_breathing_pattern(pre_analysis)

        recommendations, ai_used = self.analysis_service.ai_concise_recommendations(analysis_payload, pre_analysis)
        if not recommendations:
            recommendations = self.analysis_service.build_rule_recommendations(analysis_payload, pre_analysis)

        device_response = {
            "session_id": payload.session_id,
            "recommendations": recommendations,
            "breathing_pattern": breathing_pattern,
            "pre_analysis": pre_analysis,
            "ai_used": ai_used,
            "capture_window_summary": capture_window_summary,
            "audio_summary": audio_summary,
        }

        updated = self.repository.append_sensor_event(
            session_id=payload.session_id,
            sensor_event=payload_dict,
            pre_analysis=pre_analysis,
            device_response=device_response,
            now=now,
        )
        if not updated:
            raise SessionNotFoundError(f"Session '{payload.session_id}' not found")

        return DeviceDataResponse(
            session_id=payload.session_id,
            recommendations=recommendations,
            breathing_pattern=breathing_pattern,
            pre_analysis=RuleBasedSummary(**pre_analysis),
            ai_used=ai_used,
            capture_window_summary=(CaptureWindowSummary(**capture_window_summary) if capture_window_summary else None),
            audio_summary=(AudioSummaryIn(**audio_summary) if audio_summary else None),
        )

    def get_session(self, session_id: str) -> SessionRecordResponse:
        session = self.repository.get_session_by_id(session_id)
        if not session:
            raise SessionNotFoundError(f"Session '{session_id}' not found")
        return SessionRecordResponse(**session)

    def list_sessions(self, query: SessionListQuery) -> SessionHistoryResponse:
        items, total = self.repository.list_sessions(limit=query.limit, skip=query.skip, device_id=query.device_id)
        return SessionHistoryResponse(sessions=[SessionRecordResponse(**item) for item in items], total=total)

    def advanced_analysis(self, session_id: str, payload: AdvancedAnalysisRequest) -> AdvancedAnalysisResponse:
        session = self.repository.get_session_by_id(session_id)
        if not session:
            raise SessionNotFoundError(f"Session '{session_id}' not found")

        result, ai_used = self.analysis_service.advanced_analysis(
            session_doc=session,
            focus_areas=payload.focus_areas,
            include_environmental_context=payload.include_environmental_context,
            include_behavioral_suggestions=payload.include_behavioral_suggestions,
        )
        generated_at = utc_now()
        storage_payload = {
            **result,
            "generated_at": generated_at,
            "ai_used": ai_used,
        }
        self.repository.update_advanced_analysis(session_id, storage_payload, generated_at)

        return AdvancedAnalysisResponse(
            session_id=session_id,
            detailed_insights=result["detailed_insights"],
            recommendations=result["recommendations"],
            confidence_note=result["confidence_note"],
            generated_at=generated_at,
            ai_used=ai_used,
        )

    def dashboard(self) -> DashboardResponse:
        aggregate = self.repository.dashboard_aggregate()

        latest_highlights = [
            DashboardLatestHighlight(
                session_id=item.get("session_id", ""),
                device_id=item.get("device_id", ""),
                updated_at=item.get("updated_at", utc_now()),
                summary=(
                    (item.get("latest_pre_analysis") or {}).get("summary")
                    or "Session captured with no additional summary yet."
                ),
            )
            for item in aggregate.get("latest", [])
        ]

        trends = [
            DashboardTrendPoint(
                date=str(item.get("_id", "")),
                avg_breathing_rate=float(item.get("avg_breathing_rate") or 0.0),
                avg_snore_level=float(item.get("avg_snore_level") or 0.0),
            )
            for item in aggregate.get("trends", [])
        ]

        return DashboardResponse(
            total_sessions=int(aggregate.get("total_sessions") or 0),
            average_breathing_rate=float(aggregate.get("average_breathing_rate") or 0.0),
            average_snore_level=float(aggregate.get("average_snore_level") or 0.0),
            latest_highlights=latest_highlights,
            trends=trends,
        )
