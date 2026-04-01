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

## Device-First Flow

1. ESP32 starts a session.
2. ESP32 streams sensor data points.
3. API returns exactly three short recommendations + breathing pattern guide.
4. Mobile app reads history and requests advanced analysis on demand.
