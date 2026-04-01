from __future__ import annotations

from datetime import datetime
from typing import Any


def build_session_document(
	session_id: str,
	device_id: str,
	firmware_version: str | None,
	metadata: dict[str, Any],
	now: datetime,
) -> dict[str, Any]:
	return {
		"session_id": session_id,
		"device_id": device_id,
		"firmware_version": firmware_version,
		"metadata": metadata,
		"status": "active",
		"started_at": now,
		"updated_at": now,
		"ended_at": None,
		"sensor_events": [],
		"latest_pre_analysis": None,
		"latest_device_response": None,
		"advanced_analysis": None,
	}


def sanitize_mongo_document(document: dict[str, Any] | None) -> dict[str, Any] | None:
	if not document:
		return None

	clean_doc = dict(document)
	clean_doc.pop("_id", None)
	return clean_doc
