# API Overview

## Purpose

AGAPAI backend receives sleep-session telemetry from ESP32, stores session data in MongoDB Atlas, and provides both concise device guidance and richer mobile-app analytics.

## Base Path

- `/api`

## Main Endpoints

- `POST /api/session/start`
- `POST /api/session/data`
- `GET /api/session/{id}`
- `GET /api/sessions`
- `POST /api/session/{id}/advanced`
- `GET /api/dashboard`
- `POST /api/insight/chat`

## Device-First Flow

1. ESP32 starts a session.
2. ESP32 can either stream scalar sensor points or buffer interval samples locally during a capture window.
3. On capture-window end, ESP32 submits one summary payload with optional `capture_samples`.
4. API returns exactly three short recommendations + breathing pattern guide.
5. Mobile app reads history and requests advanced analysis on demand.

## Capture Window Payload (Optional)

`POST /api/session/data` accepts either:

- Scalar summary values (`breathing_rate`, `snore_level`, `temperature`, `humidity`), or
- A non-empty `capture_samples` list where each item includes:
  - `recorded_at`
  - `mic_raw`
  - `temperature`
  - `humidity`
  - optional `breathing_rate`, `movement_level`, `presence_detected`

When `capture_samples` is provided, backend aggregates interval samples into summary values and stores both the aggregate and raw interval list in the session event.

## Contextual Insight Chat

`POST /api/insight/chat` accepts:

- `question` (required)
- `session_id` (optional)
- `device_id` (optional)
- `store_conversation` (optional, defaults to false)

Backend always retrieves session history/context first (latest session, pre-analysis, advanced analysis, and dashboard aggregates) before generating the answer.
