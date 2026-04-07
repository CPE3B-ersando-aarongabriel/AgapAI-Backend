from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.dependencies.services import get_insight_service, get_session_service
from app.exceptions.custom_exceptions import NotFoundError
from app.schemas.insight_schema import InsightChatRequest, InsightChatResponse
from app.schemas.session_schema import (
	AdvancedAnalysisRequest,
	AdvancedAnalysisResponse,
	DashboardResponse,
	DeviceDataResponse,
	SensorDataIn,
	SessionHistoryResponse,
	SessionListQuery,
	SessionRecordResponse,
	SessionStartRequest,
	SessionStartResponse,
)
from app.services.insight_service import InsightContextNotFoundError, InsightService
from app.services.session_service import SessionNotFoundError, SessionService


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


@router.get("/session/{session_id}", response_model=SessionRecordResponse)
def get_session(
	session_id: str,
	service: SessionService = Depends(get_session_service),
) -> SessionRecordResponse:
	try:
		return service.get_session(session_id)
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
