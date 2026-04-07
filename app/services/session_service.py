from __future__ import annotations

from typing import Any

from app.models.sample_model import build_sample_document
from app.models.session_model import build_session_document
from app.repositories.session_repository import SessionRepository
from app.schemas.session_schema import (
    AdvancedAnalysisRequest,
    AdvancedAnalysisResponse,
    AudioSummaryIn,
    CaptureWindowSummary,
    DeviceSessionHistoryResponse,
    DashboardLatestHighlight,
    DashboardResponse,
    DashboardTrendPoint,
    DeviceDataResponse,
    RuleBasedSummary,
    SessionChunkRequest,
    SessionChunkResponse,
    SessionEndRequest,
    SessionEndResponse,
    SessionLiveStatusResponse,
    SensorDataIn,
    SessionHistoryResponse,
    SessionListQuery,
    SessionRecordResponse,
    SessionSummaryMetrics,
    SessionSummaryResponse,
    SessionStartRequest,
    SessionStartResponse,
)
from app.services.analysis_service import AnalysisService
from app.services.capture_service import aggregate_capture_samples
from app.utils.helpers import build_event_id, generate_session_id, normalize_sensor_payload, utc_now


class SessionNotFoundError(Exception):
    pass


class SessionClosedError(Exception):
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

    def ingest_session_chunk(self, payload: SessionChunkRequest) -> SessionChunkResponse:
        session = self.repository.get_session_by_id(payload.session_id)
        if not session:
            raise SessionNotFoundError(f"Session '{payload.session_id}' not found")
        if session.get("status") == "ended":
            raise SessionClosedError(f"Session '{payload.session_id}' already ended")

        now = utc_now()
        normalized_samples = [normalize_sensor_payload(sample.model_dump()) for sample in payload.samples]

        sample_docs = [
            build_sample_document(
                session_id=payload.session_id,
                sample=sample,
                received_at=now,
                chunk_id=payload.chunk_id,
            )
            for sample in normalized_samples
        ]

        sample_count = len(normalized_samples)
        chunk_stats = {
            "sample_count": sample_count,
            "sum_mic_raw": sum(float(s["mic_raw"]) for s in normalized_samples),
            "sum_mic_rms": sum(float(s["mic_rms"]) for s in normalized_samples),
            "max_mic_peak": max(float(s["mic_peak"]) for s in normalized_samples),
            "snore_event_count": sum(1 for s in normalized_samples if float(s["mic_raw"]) >= 45.0),
            "sum_breathing_rate": sum(float(s["breathing_rate"]) for s in normalized_samples),
            "sum_temperature": sum(float(s["temperature"]) for s in normalized_samples),
            "sum_humidity": sum(float(s["humidity"]) for s in normalized_samples),
            "last_sample_at": max(s["recorded_at"] for s in normalized_samples),
        }

        updated = self.repository.append_stream_samples(
            session_id=payload.session_id,
            sample_docs=sample_docs,
            chunk_stats=chunk_stats,
            now=now,
        )
        if not updated:
            raise SessionNotFoundError(f"Session '{payload.session_id}' not found")

        stream_stats = updated.get("stream_stats") or {}
        return SessionChunkResponse(
            session_id=payload.session_id,
            status="chunk_received",
            received_count=sample_count,
            total_samples=int(stream_stats.get("sample_count") or sample_count),
            last_recorded_at=chunk_stats["last_sample_at"],
        )

    def end_session(self, payload: SessionEndRequest) -> SessionEndResponse:
        session = self.repository.get_session_by_id(payload.session_id)
        if not session:
            raise SessionNotFoundError(f"Session '{payload.session_id}' not found")

        now = utc_now()
        ended_at = payload.ended_at or now

        device_summary = payload.summary.model_dump()
        backend_summary = normalize_sensor_payload(self.repository.compute_backend_summary(payload.session_id))
        final_summary = dict(device_summary) if device_summary.get("sample_count", 0) > 0 else dict(backend_summary)

        analysis_payload = {
            "breathing_rate": final_summary["average_breathing_rate"],
            "snore_level": final_summary["snore_score"],
            "temperature": final_summary["average_temperature"],
            "humidity": final_summary["average_humidity"],
            "movement_level": None,
            "presence_detected": None,
            "mic_raw": final_summary["average_amplitude"],
            "audio_summary": {
                "sample_count": final_summary["sample_count"],
                "average_amplitude": final_summary["average_amplitude"],
                "rms_amplitude": final_summary["rms_amplitude"],
                "peak_intensity": final_summary["peak_intensity"],
                "snore_event_count": final_summary["snore_event_count"],
                "snore_score": final_summary["snore_score"],
            },
            "recorded_at": ended_at,
        }

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
            "final_summary": final_summary,
        }

        updated = self.repository.finalize_session(
            session_id=payload.session_id,
            device_summary=device_summary,
            backend_summary=backend_summary,
            final_summary=final_summary,
            pre_analysis=pre_analysis,
            device_response=device_response,
            ended_at=ended_at,
            now=now,
        )
        if not updated:
            raise SessionNotFoundError(f"Session '{payload.session_id}' not found")

        return SessionEndResponse(
            session_id=payload.session_id,
            status="ended",
            ended_at=ended_at,
            final_summary=SessionSummaryMetrics(**final_summary),
            recommendations=recommendations,
            breathing_pattern=breathing_pattern,
            pre_analysis=RuleBasedSummary(**pre_analysis),
            ai_used=ai_used,
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

    def get_session_live_status(self, session_id: str) -> SessionLiveStatusResponse:
        live = self.repository.get_live_status(session_id)
        if not live:
            raise SessionNotFoundError(f"Session '{session_id}' not found")
        return SessionLiveStatusResponse(**live)

    def get_session_summary(self, session_id: str) -> SessionSummaryResponse:
        session = self.repository.get_session_by_id(session_id)
        if not session:
            raise SessionNotFoundError(f"Session '{session_id}' not found")

        sample_count = int((session.get("stream_stats") or {}).get("sample_count") or 0)
        device_summary_raw = session.get("device_summary")
        backend_summary_raw = session.get("backend_summary")
        final_summary_raw = session.get("final_summary")

        return SessionSummaryResponse(
            session_id=session["session_id"],
            device_id=session["device_id"],
            status=session.get("status", "active"),
            started_at=session["started_at"],
            updated_at=session["updated_at"],
            ended_at=session.get("ended_at"),
            sample_count=sample_count,
            device_summary=(SessionSummaryMetrics(**device_summary_raw) if device_summary_raw else None),
            backend_summary=(SessionSummaryMetrics(**backend_summary_raw) if backend_summary_raw else None),
            final_summary=(SessionSummaryMetrics(**final_summary_raw) if final_summary_raw else None),
            latest_pre_analysis=session.get("latest_pre_analysis"),
            latest_device_response=session.get("latest_device_response"),
        )

    def get_device_history(self, device_id: str, limit: int = 20, skip: int = 0) -> DeviceSessionHistoryResponse:
        items, total = self.repository.list_device_session_summaries(device_id=device_id, limit=limit, skip=skip)
        sessions: list[SessionSummaryResponse] = []
        for item in items:
            sample_count = int((item.get("stream_stats") or {}).get("sample_count") or 0)
            sessions.append(
                SessionSummaryResponse(
                    session_id=item["session_id"],
                    device_id=item["device_id"],
                    status=item.get("status", "active"),
                    started_at=item["started_at"],
                    updated_at=item["updated_at"],
                    ended_at=item.get("ended_at"),
                    sample_count=sample_count,
                    device_summary=(SessionSummaryMetrics(**item["device_summary"]) if item.get("device_summary") else None),
                    backend_summary=(SessionSummaryMetrics(**item["backend_summary"]) if item.get("backend_summary") else None),
                    final_summary=(SessionSummaryMetrics(**item["final_summary"]) if item.get("final_summary") else None),
                    latest_pre_analysis=item.get("latest_pre_analysis"),
                    latest_device_response=item.get("latest_device_response"),
                )
            )

        return DeviceSessionHistoryResponse(device_id=device_id, total=total, sessions=sessions)
