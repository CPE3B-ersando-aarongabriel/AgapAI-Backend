from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
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


@app.get("/health")
def health() -> dict[str, str]:
	return {"status": "healthy"}


if __name__ == "__main__":
	uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=settings.environment == "development")
