from __future__ import annotations

from datetime import datetime
from typing import Any


def build_sample_document(
	session_id: str,
	sample: dict[str, Any],
	received_at: datetime,
	chunk_id: str | None = None,
) -> dict[str, Any]:
	doc = {
		"session_id": session_id,
		"recorded_at": sample["recorded_at"],
		"mic_raw": float(sample["mic_raw"]),
		"mic_rms": float(sample["mic_rms"]),
		"mic_peak": float(sample["mic_peak"]),
		"temperature": float(sample["temperature"]),
		"humidity": float(sample["humidity"]),
		"breathing_rate": float(sample["breathing_rate"]),
		"movement_level": float(sample["movement_level"]),
		"presence_detected": bool(sample["presence_detected"]),
		"received_at": received_at,
	}
	if chunk_id:
		doc["chunk_id"] = chunk_id
	return doc


def sanitize_sample_document(document: dict[str, Any] | None) -> dict[str, Any] | None:
	if not document:
		return None
	clean = dict(document)
	clean.pop("_id", None)
	return clean
