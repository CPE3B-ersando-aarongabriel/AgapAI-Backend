# API Overview

## Purpose

AGAPAI backend receives sleep-session telemetry from ESP32, stores session data in MongoDB Atlas, and provides both concise device guidance and richer mobile-app analytics.

## Base Path

- `/api`

## Main Endpoints

- `POST /api/session/start`
- `POST /api/session/chunk`
- `POST /api/session/end`
- `GET /api/session/{id}/live`
- `GET /api/session/{id}/summary`
- `GET /api/device/{device_id}/sessions`
- `POST /api/session/data` (legacy compatibility)
- `GET /api/session/{id}`
- `GET /api/sessions`
- `POST /api/session/{id}/advanced`
- `GET /api/dashboard`
- `POST /api/insight/chat`

## Streaming Device Flow

1. ESP32 starts a session.
2. ESP32 sends lightweight chunk packets every 1-2 seconds to `/api/session/chunk`.
3. Backend stores chunk samples in a dedicated `session_samples` collection and updates running aggregates in `sessions`.
4. ESP32 stops session by sending final summary to `/api/session/end`.
5. Backend finalizes recommendations and stores `device_summary`, `backend_summary`, and `final_summary`.
6. Mobile app reads live state, summaries, and history without giant payload uploads.

## Chunk Payload

`POST /api/session/chunk` accepts:

- `session_id`
- optional `chunk_id`
- `samples` list (1..25 items) where each item includes:
  - `recorded_at`, `mic_raw`, `mic_rms`, `mic_peak`
  - `temperature`, `humidity`
  - `breathing_rate`, `movement_level`, `presence_detected`

Backend stores chunk samples as row-like records linked by `session_id`, then updates streaming stats on the session document.

## Session End Payload

`POST /api/session/end` accepts:

- `session_id`
- optional `ended_at`
- `summary` with:
  - `sample_count`
  - `average_amplitude`, `rms_amplitude`, `peak_intensity`
  - `snore_event_count`, `snore_score`
  - `average_breathing_rate`, `average_temperature`, `average_humidity`

Response includes final recommendations + breathing guide.

## Mobile Query Endpoints

- `GET /api/session/{id}/live`
  - lightweight live counters and running averages while session is active.
- `GET /api/session/{id}/summary`
  - finalized summary view (device/backend/final summary blocks).
- `GET /api/device/{device_id}/sessions`
  - efficient historical summaries for mobile list screens.

## Contextual Insight Chat

`POST /api/insight/chat` accepts:

- `question` (required)
- `session_id` (optional)
- `device_id` (optional)
- `store_conversation` (optional, defaults to false)

Backend always retrieves session history/context first (latest session, pre-analysis, advanced analysis, and dashboard aggregates) before generating the answer.
