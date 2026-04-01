from app.config.database import get_sessions_collection
from app.db.indexes.session_indexes import ensure_session_indexes


if __name__ == "__main__":
    ensure_session_indexes(get_sessions_collection())
    print("Indexes ensured for sessions collection.")
