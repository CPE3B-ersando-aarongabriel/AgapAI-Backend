# AGAPAI Backend

Production-style FastAPI backend for AGAPAI (AI Breath-Pattern Sleep Coach), designed around a device-first session workflow.

ESP32 collects data from:

- HLK-LD2410 mmWave (presence/movement)
- INMP441 microphone (snore intensity proxy)
- DHT22 (temperature/humidity)

The backend:

- Receives and validates session telemetry
- Stores session records in MongoDB Atlas
- Returns concise device-ready guidance (OLED/LED/buzzer friendly)
- Supports mobile app read-heavy session history and advanced analysis

Authentication is intentionally not implemented yet, but the codebase is layered so auth can be added later via dependencies/middleware.

## Tech Stack

- FastAPI
- PyMongo (MongoDB Atlas)
- Pydantic v2
- OpenAI Python SDK (with rule-based fallback)
- Uvicorn
- Pytest

## Project Structure

```text
app/
	api/v1/endpoints/      # HTTP route layer
	config/                # DB client and connection helpers
	core/                  # settings, constants, logging config
	db/indexes/            # Mongo index helpers
	db/seeds/              # seed scripts
	dependencies/          # reusable dependencies (DI providers)
	exceptions/            # custom app exceptions and handlers
	middleware/            # request logging and cross-cutting concerns
	models/                # Mongo document builders/mappers
	repositories/          # direct MongoDB operations
	schemas/               # Pydantic request/response models
	services/              # business logic and AI orchestration
	utils/                 # helper functions/utilities
	main.py                # FastAPI app entry point
docs/
scripts/
tests/
	integration/
	unit/
```

## Environment Variables

Copy `.env.example` to `.env` and set values:

- `APP_NAME`
- `ENVIRONMENT` (`development` or `production`)
- `API_PREFIX`
- `MONGO_URI`
- `MONGO_DB_NAME`
- `MONGO_SERVER_SELECTION_TIMEOUT_MS`
- `STARTUP_DB_CHECK`
- `STARTUP_DB_CHECK_STRICT`
- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `ENABLE_AI_PRE_ANALYSIS`
- `CORS_ORIGINS`
- `HOST`
- `PORT`
- `LOG_LEVEL`

## Local Setup

1. Create virtual environment.

Windows PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
python -m venv venv
source venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Run API locally:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## API Endpoints

### Session lifecycle

- `POST /api/session/start`
  - Creates a new session and returns `session_id`

- `POST /api/session/chunk`
  - Receives lightweight streamed chunk packets (`session_id`, `samples[]`)
  - Stores samples in dedicated `session_samples` collection
  - Updates running aggregates on the session document

- `POST /api/session/end`
  - Finalizes session with device-side summary metrics
  - Computes backend summary + final recommendations and breathing guide

- `GET /api/session/{id}/live`
  - Lightweight live status (`sample_count`, rolling averages, last sample timestamp)

- `GET /api/session/{id}/summary`
  - Returns finalized summary blocks (`device_summary`, `backend_summary`, `final_summary`)

- `GET /api/session/{id}/samples`
  - Returns paged streamed samples for charting/debug (`limit`, `skip`)

- `GET /api/device/{device_id}/sessions`
  - Efficient mobile history listing for one device

- `POST /api/session/data`
  - Legacy compatibility endpoint for older firmware payload style

- `GET /api/session/{id}`
  - Returns full single session record
  - Includes legacy-compatible `sensor_events` projection from streamed samples

- `GET /api/sessions`
  - Session history for mobile app (`limit`, `skip`, optional `device_id`)

- `POST /api/session/{id}/advanced`
  - Runs deeper analysis for app “Advanced Analysis” action
  - Stores and returns detailed insights + recommendations

- `GET /api/dashboard`
  - Aggregated analytics across sessions
  - Average breathing rate/snore level, trends, and recent highlights

- `POST /api/insight/chat`
  - Context-aware sleep insight Q&A grounded in stored backend data
  - Supports generic, device-scoped, or session-scoped questions

### Utility

- `GET /`
- `GET /health`

## MongoDB Atlas Setup

1. Create Atlas cluster.
2. Add database user and network access.
3. Copy SRV URI to `MONGO_URI`.
4. Set `MONGO_DB_NAME`.
5. Ensure indexes:

```bash
python scripts/create_indexes.py
```

Optional seed:

```bash
python scripts/seed_demo.py
```

## Render Deployment

Create a Render Web Service with:

- Python version pin:

```text
.python-version -> 3.13
```

- Build command:

```bash
pip install -r requirements.txt
```

- Start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Set environment variables in Render dashboard (`MONGO_URI`, `OPENAI_API_KEY`, `ENVIRONMENT=production`, etc.).

Recommended startup/deploy values on Render:

- `STARTUP_DB_CHECK=true`
- `STARTUP_DB_CHECK_STRICT=false` (keeps service booting while Atlas connectivity is being fixed)
- `MONGO_SERVER_SELECTION_TIMEOUT_MS=8000`

## Testing

Run tests:

```bash
pytest -q
```

## Notes

- Business logic is in `app/services`.
- Database access is isolated in `app/repositories`.
- Auth can be introduced later in `app/dependencies` and route guards without large refactor.
