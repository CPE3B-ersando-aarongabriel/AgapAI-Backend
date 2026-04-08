from __future__ import annotations

from functools import lru_cache

from pymongo.errors import PyMongoError

from app.config.database import get_session_samples_collection, get_sessions_collection
from app.exceptions.custom_exceptions import ServiceUnavailableError
from app.repositories.session_repository import SessionRepository
from app.services.analysis_service import AnalysisService
from app.services.insight_service import InsightService
from app.services.session_service import SessionService


def _ensure_indexes_or_raise(repo: SessionRepository) -> None:
    try:
        repo.ensure_indexes()
    except PyMongoError as exc:
        raise ServiceUnavailableError(
            "Database is unavailable. Check Atlas cluster state and MONGO_URI credentials."
        ) from exc


@lru_cache
def _build_service() -> SessionService:
    repo = SessionRepository(
        sessions_collection=get_sessions_collection(),
        samples_collection=get_session_samples_collection(),
    )
    _ensure_indexes_or_raise(repo)
    analysis = AnalysisService()
    return SessionService(repository=repo, analysis_service=analysis)


def get_session_service() -> SessionService:
    return _build_service()


@lru_cache
def _build_insight_service() -> InsightService:
    repo = SessionRepository(
        sessions_collection=get_sessions_collection(),
        samples_collection=get_session_samples_collection(),
    )
    _ensure_indexes_or_raise(repo)
    return InsightService(repository=repo)


def get_insight_service() -> InsightService:
    return _build_insight_service()
