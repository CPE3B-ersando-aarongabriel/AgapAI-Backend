from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from uuid import uuid4


def utc_now() -> datetime:
	return datetime.now(timezone.utc)


def generate_session_id(device_id: str) -> str:
	timestamp = utc_now().strftime("%Y%m%d%H%M%S")
	suffix = uuid4().hex[:8]
	return f"{device_id}-{timestamp}-{suffix}"


def format_timestamp(ts: datetime | None = None) -> str:
	value = ts or utc_now()
	return value.isoformat()


def normalize_sensor_value(value: float, precision: int = 2) -> float:
	return round(float(value), precision)


def normalize_sensor_payload(payload: dict) -> dict:
	normalized = dict(payload)
	for key in (
		"breathing_rate",
		"snore_level",
		"temperature",
		"humidity",
		"movement_level",
		"mic_raw",
		"avg_mic_raw",
		"max_mic_raw",
	):
		if normalized.get(key) is not None:
			normalized[key] = normalize_sensor_value(normalized[key])
	return normalized


def ensure_three_recommendations(items: list[str]) -> list[str]:
	clean = [item.strip() for item in items if item and item.strip()]
	fallback = [
		"Relax your breath with slow nasal breathing.",
		"Reduce ambient noise and keep room calm.",
		"Maintain a cool, comfortable sleep environment.",
	]
	combined = clean + fallback
	return combined[:3]


def build_event_id(session_id: str, payload: dict) -> str:
	raw = (
		f"{session_id}|{payload.get('breathing_rate')}|{payload.get('snore_level')}|"
		f"{payload.get('temperature')}|{payload.get('humidity')}|{payload.get('recorded_at')}"
	)
	return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
