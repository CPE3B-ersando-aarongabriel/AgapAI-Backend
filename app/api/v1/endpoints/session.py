from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.dependencies.services import get_insight_service, get_session_service
from app.exceptions.custom_exceptions import ConflictError, NotFoundError
from app.schemas.insight_schema import InsightChatRequest, InsightChatResponse
from app.schemas.session_schema import (
	AdvancedAnalysisRequest,
	AdvancedAnalysisResponse,
	DeviceSessionHistoryResponse,
	DashboardResponse,
	DeviceDataResponse,
	SessionChunkRequest,
	SessionChunkResponse,
	SessionEndRequest,
	SessionEndResponse,
	SensorDataIn,
	SessionHistoryResponse,
	SessionLiveStatusResponse,
	SessionListQuery,
	SessionRecordResponse,
	SessionSummaryResponse,
	SessionStartRequest,
	SessionStartResponse,
)
from app.services.insight_service import InsightContextNotFoundError, InsightService
from app.services.session_service import SessionClosedError, SessionNotFoundError, SessionService


router = APIRouter(prefix="/api", tags=["Endpoints"])


@router.post("/session/start", response_model=SessionStartResponse)
def start_session(
	payload: SessionStartRequest,
	service: SessionService = Depends(get_session_service),
) -> SessionStartResponse:
	return service.start_session(payload)


@router.post("/session/data", response_model=DeviceDataResponse)
def post_session_data(
	payload: SensorDataIn,
	service: SessionService = Depends(get_session_service),
) -> DeviceDataResponse:
	try:
		return service.ingest_sensor_data(payload)
	except SessionNotFoundError as exc:
		raise NotFoundError(str(exc)) from exc


@router.post("/session/chunk", response_model=SessionChunkResponse)
def post_session_chunk(
	payload: SessionChunkRequest,
	service: SessionService = Depends(get_session_service),
) -> SessionChunkResponse:
	try:
		return service.ingest_session_chunk(payload)
	except SessionNotFoundError as exc:
		raise NotFoundError(str(exc)) from exc
	except SessionClosedError as exc:
		raise ConflictError(str(exc)) from exc


@router.post("/session/end", response_model=SessionEndResponse)
def post_session_end(
	payload: SessionEndRequest,
	service: SessionService = Depends(get_session_service),
) -> SessionEndResponse:
	try:
		return service.end_session(payload)
	except SessionNotFoundError as exc:
		raise NotFoundError(str(exc)) from exc
	except SessionClosedError as exc:
		raise ConflictError(str(exc)) from exc


@router.get("/session/{session_id}", response_model=SessionRecordResponse)
def get_session(
	session_id: str,
	service: SessionService = Depends(get_session_service),
) -> SessionRecordResponse:
	try:
		return service.get_session(session_id)
	except SessionNotFoundError as exc:
		raise NotFoundError(str(exc)) from exc


@router.get("/session/{session_id}/summary", response_model=SessionSummaryResponse)
def get_session_summary(
	session_id: str,
	service: SessionService = Depends(get_session_service),
) -> SessionSummaryResponse:
	try:
		return service.get_session_summary(session_id)
	except SessionNotFoundError as exc:
		raise NotFoundError(str(exc)) from exc


@router.get("/session/{session_id}/live", response_model=SessionLiveStatusResponse)
def get_session_live(
	session_id: str,
	service: SessionService = Depends(get_session_service),
) -> SessionLiveStatusResponse:
	try:
		return service.get_session_live_status(session_id)
	except SessionNotFoundError as exc:
		raise NotFoundError(str(exc)) from exc


@router.get("/sessions", response_model=SessionHistoryResponse)
def list_sessions(
	limit: int = Query(default=20, ge=1, le=100),
	skip: int = Query(default=0, ge=0),
	device_id: str | None = Query(default=None),
	service: SessionService = Depends(get_session_service),
) -> SessionHistoryResponse:
	return service.list_sessions(SessionListQuery(limit=limit, skip=skip, device_id=device_id))


@router.get("/device/{device_id}/sessions", response_model=DeviceSessionHistoryResponse)
def get_device_sessions(
	device_id: str,
	limit: int = Query(default=20, ge=1, le=100),
	skip: int = Query(default=0, ge=0),
	service: SessionService = Depends(get_session_service),
) -> DeviceSessionHistoryResponse:
	return service.get_device_history(device_id=device_id, limit=limit, skip=skip)


@router.post("/session/{session_id}/advanced", response_model=AdvancedAnalysisResponse)
def run_advanced_analysis(
	session_id: str,
	payload: AdvancedAnalysisRequest,
	service: SessionService = Depends(get_session_service),
) -> AdvancedAnalysisResponse:
	try:
		return service.advanced_analysis(session_id, payload)
	except SessionNotFoundError as exc:
		raise NotFoundError(str(exc)) from exc


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(service: SessionService = Depends(get_session_service)) -> DashboardResponse:
	return service.dashboard()


@router.post("/insight/chat", response_model=InsightChatResponse)
def ask_sleep_insight(
	payload: InsightChatRequest,
	service: InsightService = Depends(get_insight_service),
) -> InsightChatResponse:
	try:
		return service.ask(payload)
	except InsightContextNotFoundError as exc:
		raise NotFoundError(str(exc)) from exc
