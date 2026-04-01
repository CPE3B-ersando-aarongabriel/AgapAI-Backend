from __future__ import annotations

from functools import lru_cache

from app.config.database import get_sessions_collection
from app.repositories.session_repository import SessionRepository
from app.services.analysis_service import AnalysisService
from app.services.session_service import SessionService


@lru_cache
def _build_service() -> SessionService:
    repo = SessionRepository(get_sessions_collection())
    repo.ensure_indexes()
    analysis = AnalysisService()
    return SessionService(repository=repo, analysis_service=analysis)


def get_session_service() -> SessionService:
    return _build_service()
