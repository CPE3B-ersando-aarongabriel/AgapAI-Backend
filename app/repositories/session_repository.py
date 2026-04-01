from __future__ import annotations

from datetime import datetime
from typing import Any

from pymongo import ASCENDING, DESCENDING
from pymongo.collection import Collection

from app.models.session_model import sanitize_mongo_document


class SessionRepository:
    def __init__(self, collection: Collection):
        self.collection = collection

    def ensure_indexes(self) -> None:
        self.collection.create_index([("session_id", ASCENDING)], unique=True, name="uniq_session_id")
        self.collection.create_index([("updated_at", DESCENDING)], name="idx_updated_at_desc")
        self.collection.create_index([("started_at", DESCENDING)], name="idx_started_at_desc")
        self.collection.create_index([("device_id", ASCENDING)], name="idx_device_id")

    def create_session(self, document: dict[str, Any]) -> dict[str, Any]:
        self.collection.update_one(
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
        self.collection.update_one(
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

    def update_advanced_analysis(self, session_id: str, payload: dict[str, Any], now: datetime) -> dict[str, Any] | None:
        self.collection.update_one(
            {"session_id": session_id},
            {"$set": {"advanced_analysis": payload, "updated_at": now}},
        )
        return self.get_session_by_id(session_id)

    def get_session_by_id(self, session_id: str) -> dict[str, Any] | None:
        doc = self.collection.find_one({"session_id": session_id})
        return sanitize_mongo_document(doc)

    def list_sessions(self, limit: int, skip: int, device_id: str | None = None) -> tuple[list[dict[str, Any]], int]:
        query: dict[str, Any] = {}
        if device_id:
            query["device_id"] = device_id

        cursor = (
            self.collection.find(query)
            .sort("updated_at", DESCENDING)
            .skip(skip)
            .limit(limit)
        )
        items = [sanitize_mongo_document(doc) for doc in cursor]
        total = self.collection.count_documents(query)
        return [item for item in items if item is not None], total

    def dashboard_aggregate(self) -> dict[str, Any]:
        total_sessions = self.collection.count_documents({})

        avg_pipeline = [
            {"$unwind": {"path": "$sensor_events", "preserveNullAndEmptyArrays": False}},
            {
                "$group": {
                    "_id": None,
                    "avg_breathing_rate": {"$avg": "$sensor_events.breathing_rate"},
                    "avg_snore_level": {"$avg": "$sensor_events.snore_level"},
                }
            },
        ]
        avg_result = list(self.collection.aggregate(avg_pipeline))
        averages = avg_result[0] if avg_result else {"avg_breathing_rate": 0.0, "avg_snore_level": 0.0}

        latest_docs = (
            self.collection.find({})
            .sort("updated_at", DESCENDING)
            .limit(5)
        )
        latest = [sanitize_mongo_document(doc) for doc in latest_docs]

        trend_pipeline = [
            {"$unwind": {"path": "$sensor_events", "preserveNullAndEmptyArrays": False}},
            {
                "$addFields": {
                    "event_date": {
                        "$dateToString": {"format": "%Y-%m-%d", "date": "$sensor_events.recorded_at"}
                    }
                }
            },
            {
                "$group": {
                    "_id": "$event_date",
                    "avg_breathing_rate": {"$avg": "$sensor_events.breathing_rate"},
                    "avg_snore_level": {"$avg": "$sensor_events.snore_level"},
                }
            },
            {"$sort": {"_id": 1}},
            {"$limit": 14},
        ]
        trends = list(self.collection.aggregate(trend_pipeline))

        return {
            "total_sessions": total_sessions,
            "average_breathing_rate": float(averages.get("avg_breathing_rate") or 0.0),
            "average_snore_level": float(averages.get("avg_snore_level") or 0.0),
            "latest": [item for item in latest if item is not None],
            "trends": trends,
        }
