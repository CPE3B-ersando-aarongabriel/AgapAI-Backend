from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.schemas.session_schema import SensorDataIn
from app.services.capture_service import aggregate_capture_samples


BASE_TS = datetime(2026, 4, 7, 0, 0, tzinfo=timezone.utc)


def test_sensor_data_accepts_capture_samples_without_scalar_summary() -> None:
    payload = SensorDataIn(
        session_id="esp32-20260407000000-abcd1234",
        capture_samples=[
            {
                "recorded_at": BASE_TS,
                "mic_raw": 580.0,
                "temperature": 26.1,
                "humidity": 59.0,
                "breathing_rate": 15.2,
                "movement_level": 3.1,
                "presence_detected": True,
            }
        ],
    )

    assert payload.capture_samples[0].mic_raw == 580.0
    assert payload.breathing_rate is None


def test_aggregate_capture_samples_builds_non_zero_summary() -> None:
    samples = [
        {
            "recorded_at": BASE_TS,
            "mic_raw": 500.0,
            "temperature": 26.0,
            "humidity": 58.0,
            "breathing_rate": 14.0,
            "movement_level": 2.0,
            "presence_detected": True,
        },
        {
            "recorded_at": BASE_TS + timedelta(seconds=2),
            "mic_raw": 900.0,
            "temperature": 26.4,
            "humidity": 58.5,
            "breathing_rate": 15.0,
            "movement_level": 4.0,
            "presence_detected": True,
        },
        {
            "recorded_at": BASE_TS + timedelta(seconds=4),
            "mic_raw": 1250.0,
            "temperature": 26.8,
            "humidity": 59.5,
            "breathing_rate": 16.0,
            "movement_level": 5.0,
            "presence_detected": True,
        },
    ]

    aggregated = aggregate_capture_samples(samples)

    assert aggregated.summarized_values["sample_count"] == 3
    assert aggregated.summarized_values["avg_mic_raw"] > 0
    assert aggregated.summarized_values["snore_level"] > 0
    assert aggregated.window_summary["window_started_at"] == BASE_TS
    assert aggregated.window_summary["window_ended_at"] == BASE_TS + timedelta(seconds=4)


def test_aggregate_capture_samples_rejects_empty_list() -> None:
    with pytest.raises(ValueError):
        aggregate_capture_samples([])


def test_aggregate_capture_samples_supports_scaled_mic_range() -> None:
    samples = [
        {
            "recorded_at": BASE_TS,
            "mic_raw": 18.0,
            "mic_rms": 22.0,
            "mic_peak": 34.0,
            "temperature": 25.8,
            "humidity": 57.0,
            "breathing_rate": 13.0,
            "movement_level": 3.0,
            "presence_detected": True,
        },
        {
            "recorded_at": BASE_TS + timedelta(seconds=2),
            "mic_raw": 42.0,
            "mic_rms": 46.0,
            "mic_peak": 60.0,
            "temperature": 26.2,
            "humidity": 58.0,
            "breathing_rate": 14.0,
            "movement_level": 4.0,
            "presence_detected": True,
        },
        {
            "recorded_at": BASE_TS + timedelta(seconds=4),
            "mic_raw": 76.0,
            "mic_rms": 80.0,
            "mic_peak": 93.0,
            "temperature": 26.5,
            "humidity": 59.0,
            "breathing_rate": 15.0,
            "movement_level": 5.0,
            "presence_detected": True,
        },
    ]

    aggregated = aggregate_capture_samples(samples)

    assert aggregated.audio_summary["sample_count"] == 3
    assert aggregated.audio_summary["average_amplitude"] > 0
    assert aggregated.audio_summary["snore_score"] > 0
