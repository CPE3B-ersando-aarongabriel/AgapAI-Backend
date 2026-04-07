from __future__ import annotations

from datetime import datetime
from typing import Any

from pymongo import ASCENDING, DESCENDING
from pymongo.collection import Collection

from app.models.session_model import sanitize_mongo_document
from app.models.sample_model import sanitize_sample_document


class SessionRepository:
    def __init__(self, sessions_collection: Collection, samples_collection: Collection):
        self.sessions_collection = sessions_collection
        self.samples_collection = samples_collection

    def ensure_indexes(self) -> None:
        self.sessions_collection.create_index([("session_id", ASCENDING)], unique=True, name="uniq_session_id")
        self.sessions_collection.create_index([("updated_at", DESCENDING)], name="idx_updated_at_desc")
        self.sessions_collection.create_index([("started_at", DESCENDING)], name="idx_started_at_desc")
        self.sessions_collection.create_index([("device_id", ASCENDING)], name="idx_device_id")
        self.sessions_collection.create_index([("status", ASCENDING)], name="idx_status")

        self.samples_collection.create_index([("session_id", ASCENDING), ("recorded_at", ASCENDING)], name="idx_session_recorded")
        self.samples_collection.create_index([("session_id", ASCENDING), ("received_at", DESCENDING)], name="idx_session_received_desc")

    def create_session(self, document: dict[str, Any]) -> dict[str, Any]:
        self.sessions_collection.update_one(
            {"session_id": document["session_id"]},
            {"$setOnInsert": document},
            upsert=True,
        )
        return self.get_session_by_id(document["session_id"]) or document

    def append_sensor_event(
        self,
        session_id: str,
        sensor_event: dict[str, Any],
        pre_analysis: dict[str, Any],
        device_response: dict[str, Any],
        now: datetime,
    ) -> dict[str, Any] | None:
        self.sessions_collection.update_one(
            {"session_id": session_id},
            {
                "$set": {
                    "updated_at": now,
                    "latest_pre_analysis": pre_analysis,
                    "latest_device_response": device_response,
                },
                "$addToSet": {"sensor_events": sensor_event},
            },
        )
        return self.get_session_by_id(session_id)

    def append_stream_samples(
        self,
        session_id: str,
        sample_docs: list[dict[str, Any]],
        chunk_stats: dict[str, float | int | datetime],
        now: datetime,
    ) -> dict[str, Any] | None:
        if not sample_docs:
            return self.get_session_by_id(session_id)

        self.samples_collection.insert_many(sample_docs, ordered=False)

        self.sessions_collection.update_one(
            {"session_id": session_id},
            {
                "$set": {
                    "updated_at": now,
                    "last_sample_at": chunk_stats["last_sample_at"],
                },
                "$inc": {
                    "stream_stats.sample_count": int(chunk_stats["sample_count"]),
                    "stream_stats.sum_mic_raw": float(chunk_stats["sum_mic_raw"]),
                    "stream_stats.sum_mic_rms": float(chunk_stats["sum_mic_rms"]),
                    "stream_stats.snore_event_count": int(chunk_stats["snore_event_count"]),
                    "stream_stats.sum_breathing_rate": float(chunk_stats["sum_breathing_rate"]),
                    "stream_stats.sum_temperature": float(chunk_stats["sum_temperature"]),
                    "stream_stats.sum_humidity": float(chunk_stats["sum_humidity"]),
                },
                "$max": {"stream_stats.max_mic_peak": float(chunk_stats["max_mic_peak"])},
            },
        )
        return self.get_session_by_id(session_id)

    def compute_backend_summary(self, session_id: str) -> dict[str, Any]:
        session = self.get_session_by_id(session_id)
        if not session:
            return {
                "sample_count": 0,
                "average_amplitude": 0.0,
                "rms_amplitude": 0.0,
                "peak_intensity": 0.0,
                "snore_event_count": 0,
                "snore_score": 0.0,
                "average_breathing_rate": 0.0,
                "average_temperature": 0.0,
                "average_humidity": 0.0,
            }

        stats = session.get("stream_stats") or {}
        sample_count = int(stats.get("sample_count") or 0)
        if sample_count <= 0:
            return {
                "sample_count": 0,
                "average_amplitude": 0.0,
                "rms_amplitude": 0.0,
                "peak_intensity": 0.0,
                "snore_event_count": 0,
                "snore_score": 0.0,
                "average_breathing_rate": 0.0,
                "average_temperature": 0.0,
                "average_humidity": 0.0,
            }

        average_amplitude = float(stats.get("sum_mic_raw") or 0.0) / sample_count
        rms_amplitude = float(stats.get("sum_mic_rms") or 0.0) / sample_count
        peak_intensity = float(stats.get("max_mic_peak") or 0.0)
        snore_event_count = int(stats.get("snore_event_count") or 0)
        average_breathing_rate = float(stats.get("sum_breathing_rate") or 0.0) / sample_count
        average_temperature = float(stats.get("sum_temperature") or 0.0) / sample_count
        average_humidity = float(stats.get("sum_humidity") or 0.0) / sample_count
        snore_score = min(100.0, average_amplitude * 1.4)

        return {
            "sample_count": sample_count,
            "average_amplitude": average_amplitude,
            "rms_amplitude": rms_amplitude,
            "peak_intensity": peak_intensity,
            "snore_event_count": snore_event_count,
            "snore_score": snore_score,
            "average_breathing_rate": average_breathing_rate,
            "average_temperature": average_temperature,
            "average_humidity": average_humidity,
        }

    def finalize_session(
        self,
        session_id: str,
        device_summary: dict[str, Any],
        backend_summary: dict[str, Any],
        final_summary: dict[str, Any],
        pre_analysis: dict[str, Any],
        device_response: dict[str, Any],
        ended_at: datetime,
        now: datetime,
    ) -> dict[str, Any] | None:
        self.sessions_collection.update_one(
            {"session_id": session_id},
            {
                "$set": {
                    "status": "ended",
                    "ended_at": ended_at,
                    "updated_at": now,
                    "device_summary": device_summary,
                    "backend_summary": backend_summary,
                    "final_summary": final_summary,
                    "latest_pre_analysis": pre_analysis,
                    "latest_device_response": device_response,
                }
            },
        )
        return self.get_session_by_id(session_id)

    def get_live_status(self, session_id: str) -> dict[str, Any] | None:
        session = self.get_session_by_id(session_id)
        if not session:
            return None

        stats = session.get("stream_stats") or {}
        sample_count = int(stats.get("sample_count") or 0)

        if sample_count <= 0:
            avg_amplitude = 0.0
            avg_rms = 0.0
            avg_br = 0.0
            avg_temp = 0.0
            avg_hum = 0.0
        else:
            avg_amplitude = float(stats.get("sum_mic_raw") or 0.0) / sample_count
            avg_rms = float(stats.get("sum_mic_rms") or 0.0) / sample_count
            avg_br = float(stats.get("sum_breathing_rate") or 0.0) / sample_count
            avg_temp = float(stats.get("sum_temperature") or 0.0) / sample_count
            avg_hum = float(stats.get("sum_humidity") or 0.0) / sample_count

        return {
            "session_id": session_id,
            "device_id": session.get("device_id"),
            "status": session.get("status", "active"),
            "started_at": session.get("started_at"),
            "updated_at": session.get("updated_at"),
            "last_sample_at": session.get("last_sample_at"),
            "sample_count": sample_count,
            "average_amplitude": avg_amplitude,
            "rms_amplitude": avg_rms,
            "peak_intensity": float(stats.get("max_mic_peak") or 0.0),
            "snore_event_count": int(stats.get("snore_event_count") or 0),
            "average_breathing_rate": avg_br,
            "average_temperature": avg_temp,
            "average_humidity": avg_hum,
        }

    def get_session_samples(self, session_id: str, limit: int, skip: int) -> tuple[list[dict[str, Any]], int]:
        query = {"session_id": session_id}
        cursor = (
            self.samples_collection.find(query)
            .sort("recorded_at", ASCENDING)
            .skip(skip)
            .limit(limit)
        )
        items = [sanitize_sample_document(doc) for doc in cursor]
        total = self.samples_collection.count_documents(query)
        return [item for item in items if item is not None], total

    def list_device_session_summaries(self, device_id: str, limit: int, skip: int) -> tuple[list[dict[str, Any]], int]:
        query = {"device_id": device_id}
        cursor = (
            self.sessions_collection.find(query)
            .sort("started_at", DESCENDING)
            .skip(skip)
            .limit(limit)
        )
        items = [sanitize_mongo_document(doc) for doc in cursor]
        total = self.sessions_collection.count_documents(query)
        return [item for item in items if item is not None], total

    def update_advanced_analysis(self, session_id: str, payload: dict[str, Any], now: datetime) -> dict[str, Any] | None:
        self.sessions_collection.update_one(
            {"session_id": session_id},
            {"$set": {"advanced_analysis": payload, "updated_at": now}},
        )
        return self.get_session_by_id(session_id)

    def get_session_by_id(self, session_id: str) -> dict[str, Any] | None:
        doc = self.sessions_collection.find_one({"session_id": session_id})
        return sanitize_mongo_document(doc)

    def get_latest_session(self, device_id: str | None = None) -> dict[str, Any] | None:
        query: dict[str, Any] = {}
        if device_id:
            query["device_id"] = device_id

        doc = self.sessions_collection.find_one(query, sort=[("updated_at", DESCENDING)])
        return sanitize_mongo_document(doc)

    def list_sessions(self, limit: int, skip: int, device_id: str | None = None) -> tuple[list[dict[str, Any]], int]:
        query: dict[str, Any] = {}
        if device_id:
            query["device_id"] = device_id

        cursor = (
            self.sessions_collection.find(query)
            .sort("updated_at", DESCENDING)
            .skip(skip)
            .limit(limit)
        )
        items = [sanitize_mongo_document(doc) for doc in cursor]
        total = self.sessions_collection.count_documents(query)
        return [item for item in items if item is not None], total

    def append_insight_history(self, session_id: str, entry: dict[str, Any], now: datetime) -> dict[str, Any] | None:
        self.sessions_collection.update_one(
            {"session_id": session_id},
            {
                "$set": {"updated_at": now},
                "$push": {"insight_history": entry},
            },
        )
        return self.get_session_by_id(session_id)

    def _build_sample_query(self, device_id: str | None = None) -> dict[str, Any]:
        if not device_id:
            return {}

        cursor = self.sessions_collection.find({"device_id": device_id}, {"session_id": 1})
        session_ids = [doc.get("session_id") for doc in cursor if doc.get("session_id")]
        return {"session_id": {"$in": session_ids or ["__none__"]}}

    def dashboard_aggregate(self, device_id: str | None = None) -> dict[str, Any]:
        query: dict[str, Any] = {}
        if device_id:
            query["device_id"] = device_id

        total_sessions = self.sessions_collection.count_documents(query)
        sample_query = self._build_sample_query(device_id)

        avg_pipeline = [
            {"$match": sample_query},
            {
                "$group": {
                    "_id": None,
                    "avg_breathing_rate": {"$avg": "$breathing_rate"},
                    "avg_snore_level": {"$avg": "$mic_raw"},
                }
            },
        ]
        avg_result = list(self.samples_collection.aggregate(avg_pipeline))
        averages = avg_result[0] if avg_result else {"avg_breathing_rate": 0.0, "avg_snore_level": 0.0}

        latest_docs = (
            self.sessions_collection.find(query)
            .sort("updated_at", DESCENDING)
            .limit(5)
        )
        latest = [sanitize_mongo_document(doc) for doc in latest_docs]

        trend_pipeline = [
            {"$match": sample_query},
            {
                "$addFields": {
                    "event_date": {
                        "$dateToString": {"format": "%Y-%m-%d", "date": "$recorded_at"}
                    }
                }
            },
            {
                "$group": {
                    "_id": "$event_date",
                    "avg_breathing_rate": {"$avg": "$breathing_rate"},
                    "avg_snore_level": {"$avg": "$mic_raw"},
                }
            },
            {"$sort": {"_id": 1}},
            {"$limit": 14},
        ]
        trends = list(self.samples_collection.aggregate(trend_pipeline))

        return {
            "total_sessions": total_sessions,
            "average_breathing_rate": float(averages.get("avg_breathing_rate") or 0.0),
            "average_snore_level": float(averages.get("avg_snore_level") or 0.0),
            "latest": [item for item in latest if item is not None],
            "trends": trends,
        }
