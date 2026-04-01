from __future__ import annotations

from app.config.database import get_sessions_collection
from app.models.session_model import build_session_document
from app.utils.helpers import utc_now


def seed_demo_session() -> None:
    collection = get_sessions_collection()
    now = utc_now()
    doc = build_session_document(
        session_id="demo-session-001",
        device_id="esp32-demo",
        firmware_version="0.1.0",
        metadata={"seed": True},
        now=now,
    )
    collection.update_one(
        {"session_id": doc["session_id"]},
        {"$setOnInsert": doc},
        upsert=True,
    )


if __name__ == "__main__":
    seed_demo_session()
