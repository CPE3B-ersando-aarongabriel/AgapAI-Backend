from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError

from app.exceptions.custom_exceptions import AppError
from app.utils.helpers import utc_now


logger = logging.getLogger("agapai")


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": "application_error",
                "detail": exc.message,
                "code": exc.status_code,
                "timestamp": utc_now().isoformat(),
            },
        )

    @app.exception_handler(PyMongoError)
    async def mongo_error_handler(_: Request, exc: PyMongoError) -> JSONResponse:
        logger.warning("MongoDB operation failed: %s", exc)
        return JSONResponse(
            status_code=503,
            content={
                "error": "database_unavailable",
                "detail": "Database is unavailable. Check Atlas cluster state and MONGO_URI credentials.",
                "code": 503,
                "timestamp": utc_now().isoformat(),
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception during request", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_server_error",
                "detail": "Unexpected server error",
                "code": 500,
                "timestamp": utc_now().isoformat(),
            },
        )
