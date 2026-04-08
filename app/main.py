from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from pymongo.errors import PyMongoError

from app.api.v1.endpoints.session import router as session_router
from app.config.database import close_mongo_connection, get_client
from app.core.logging_config import configure_logging
from app.core.settings import get_settings
from app.exceptions.handlers import register_exception_handlers
from app.middleware.logging_middleware import RequestLoggingMiddleware


settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger("agapai")


@asynccontextmanager
async def lifespan(_: FastAPI):
	# Startup hook where DB connectivity and indexes are initialized.
	if settings.startup_db_check:
		try:
			get_client().admin.command("ping")
			logger.info("MongoDB connection established.")
		except PyMongoError as exc:
			if settings.startup_db_check_strict:
				logger.exception("MongoDB startup check failed and strict mode is enabled.")
				raise
			logger.warning(
				"MongoDB startup check failed; continuing startup because strict mode is disabled: %s",
				exc,
			)
	else:
		logger.info("MongoDB startup check disabled by STARTUP_DB_CHECK.")

	logger.info("Starting %s in %s mode", settings.app_name, settings.environment)
	yield
	close_mongo_connection()
	logger.info("MongoDB connection closed.")


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
	CORSMiddleware,
	allow_origins=settings.cors_origin_list,
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)
app.add_middleware(RequestLoggingMiddleware)

app.include_router(session_router)
register_exception_handlers(app)


@app.get("/")
def root() -> dict[str, str]:
	return {
		"service": settings.app_name,
		"environment": settings.environment,
		"status": "ok",
	}


@app.head("/", include_in_schema=False)
def root_head() -> Response:
	return Response(status_code=200)


@app.get("/health")
def health() -> dict[str, str]:
	return {"status": "healthy"}


def _resolve_runtime_port() -> int:
	raw_port = os.environ.get("PORT")
	if not raw_port:
		return settings.port
	try:
		return int(raw_port)
	except ValueError:
		logger.warning("Invalid PORT value '%s'; falling back to settings port %s", raw_port, settings.port)
		return settings.port


def _resolve_runtime_host() -> str:
	return os.environ.get("HOST") or "0.0.0.0"


if __name__ == "__main__":
	host = _resolve_runtime_host()
	port = _resolve_runtime_port()
	logger.info("Launching Uvicorn with host=%s port=%s", host, port)
	uvicorn.run("app.main:app", host=host, port=port, reload=settings.environment == "development")
