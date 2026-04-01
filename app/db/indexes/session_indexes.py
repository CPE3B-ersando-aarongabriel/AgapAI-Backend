from __future__ import annotations

from pymongo import ASCENDING, DESCENDING
from pymongo.collection import Collection


def ensure_session_indexes(collection: Collection) -> None:
    collection.create_index([("session_id", ASCENDING)], unique=True, name="uniq_session_id")
    collection.create_index([("started_at", DESCENDING)], name="idx_started_at_desc")
    collection.create_index([("updated_at", DESCENDING)], name="idx_updated_at_desc")
    collection.create_index([("device_id", ASCENDING)], name="idx_device_id")
