from __future__ import annotations

import certifi
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from app.core.settings import get_settings


_client: MongoClient | None = None


def get_client() -> MongoClient:
	global _client

	if _client is None:
		settings = get_settings()
		client_kwargs: dict[str, object] = {
			"serverSelectionTimeoutMS": settings.mongo_server_selection_timeout_ms,
		}

		if settings.mongo_uri.startswith("mongodb+srv://"):
			# Explicitly provide CA bundle for TLS verification in containerized deploys.
			client_kwargs["tlsCAFile"] = certifi.where()

		_client = MongoClient(settings.mongo_uri, **client_kwargs)
	return _client


def get_database() -> Database:
	settings = get_settings()
	return get_client()[settings.mongo_db_name]


def get_sessions_collection() -> Collection:
	return get_database()["sessions"]


def close_mongo_connection() -> None:
	global _client
	if _client is not None:
		_client.close()
		_client = None
