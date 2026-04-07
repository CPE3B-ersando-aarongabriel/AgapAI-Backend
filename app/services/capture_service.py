from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


MIC_NOISE_FLOOR = 120.0
MIC_LOUD_LEVEL = 2500.0
MIC_NOISE_FLOOR_SCALED = 8.0
MIC_LOUD_LEVEL_SCALED = 90.0


@dataclass(frozen=True)
class CaptureAggregationResult:
    summarized_values: dict[str, Any]
    window_summary: dict[str, Any]
    audio_summary: dict[str, Any]
    normalized_samples: list[dict[str, Any]]


def _clamp(value: float, minimum: float, maximum: float) -> float:
    if value < minimum:
        return minimum
    if value > maximum:
        return maximum
    return value


def _avg(values: list[float], fallback: float) -> float:
    if not values:
        return fallback
    return sum(values) / len(values)


def _majority_true(values: list[bool], fallback: bool = True) -> bool:
    if not values:
        return fallback
    return sum(1 for value in values if value) >= len(values) / 2


def _normalize_snore_from_mic(avg_mic_raw: float) -> float:
    normalized = ((avg_mic_raw - MIC_NOISE_FLOOR) / (MIC_LOUD_LEVEL - MIC_NOISE_FLOOR)) * 100.0
    return _clamp(normalized, 0.0, 100.0)


def _resolve_mic_scale(mic_values: list[float]) -> tuple[float, float]:
    if not mic_values:
        return MIC_NOISE_FLOOR_SCALED, MIC_LOUD_LEVEL_SCALED

    peak = max(mic_values)
    # New firmware emits mic metrics in a normalized 0-100 range.
    if peak <= 120.0:
        return MIC_NOISE_FLOOR_SCALED, MIC_LOUD_LEVEL_SCALED

    # Legacy uploads may still send larger raw ranges.
    return MIC_NOISE_FLOOR, MIC_LOUD_LEVEL


def _rms(values: list[float], fallback: float) -> float:
    if not values:
        return fallback
    return math.sqrt(sum(value * value for value in values) / len(values))


def aggregate_capture_samples(samples: list[dict[str, Any]]) -> CaptureAggregationResult:
    if not samples:
        raise ValueError("capture_samples cannot be empty")

    normalized_samples = sorted(samples, key=lambda item: item["recorded_at"])

    mic_values = [float(item["mic_raw"]) for item in normalized_samples if item.get("mic_raw") is not None]
    mic_rms_values = [float(item["mic_rms"]) for item in normalized_samples if item.get("mic_rms") is not None]
    mic_peak_values = [float(item["mic_peak"]) for item in normalized_samples if item.get("mic_peak") is not None]
    temp_values = [float(item["temperature"]) for item in normalized_samples if item.get("temperature") is not None]
    humidity_values = [float(item["humidity"]) for item in normalized_samples if item.get("humidity") is not None]
    breathing_values = [
        float(item["breathing_rate"])
        for item in normalized_samples
        if item.get("breathing_rate") is not None
    ]
    movement_values = [
        float(item["movement_level"])
        for item in normalized_samples
        if item.get("movement_level") is not None
    ]
    presence_values = [
        bool(item["presence_detected"])
        for item in normalized_samples
        if item.get("presence_detected") is not None
    ]

    avg_mic_raw = max(0.0, _avg(mic_values, fallback=0.0))
    rms_mic = max(0.0, _rms(mic_rms_values or mic_values, fallback=0.0))
    peak_mic = max(mic_peak_values or mic_values) if (mic_peak_values or mic_values) else 0.0

    mic_floor, mic_loud = _resolve_mic_scale(mic_values)
    mic_span = max(mic_loud - mic_floor, 1.0)

    event_threshold = max(mic_floor * 1.5, avg_mic_raw * 1.35)
    snore_event_count = sum(1 for value in mic_values if value >= event_threshold)

    amp_norm = _clamp((avg_mic_raw - mic_floor) / mic_span, 0.0, 1.0)
    rms_norm = _clamp((rms_mic - mic_floor) / mic_span, 0.0, 1.0)
    peak_norm = _clamp((peak_mic - mic_floor) / max((mic_loud * 1.5) - mic_floor, 1.0), 0.0, 1.0)
    density_norm = _clamp(snore_event_count / max(len(normalized_samples), 1), 0.0, 1.0)

    snore_score = round((0.35 * amp_norm + 0.25 * rms_norm + 0.25 * peak_norm + 0.15 * density_norm) * 100.0, 2)

    audio_summary = {
        "sample_count": len(normalized_samples),
        "average_amplitude": round(avg_mic_raw, 2),
        "rms_amplitude": round(rms_mic, 2),
        "peak_intensity": round(peak_mic, 2),
        "snore_event_count": snore_event_count,
        "snore_score": snore_score,
    }

    summarized_values = {
        "breathing_rate": round(_clamp(_avg(breathing_values, fallback=14.0), 0.0, 60.0), 2),
        "snore_level": snore_score,
        "temperature": round(_clamp(_avg(temp_values, fallback=25.0), 5.0, 45.0), 2),
        "humidity": round(_clamp(_avg(humidity_values, fallback=55.0), 0.0, 100.0), 2),
        "movement_level": round(_clamp(_avg(movement_values, fallback=0.0), 0.0, 100.0), 2),
        "presence_detected": _majority_true(presence_values, fallback=True),
        "avg_mic_raw": round(avg_mic_raw, 2),
        "max_mic_raw": round(peak_mic, 2),
        "sample_count": len(normalized_samples),
        "audio_summary": audio_summary,
    }

    window_summary = {
        "sample_count": len(normalized_samples),
        "window_started_at": normalized_samples[0]["recorded_at"],
        "window_ended_at": normalized_samples[-1]["recorded_at"],
        "avg_mic_raw": round(avg_mic_raw, 2),
        "max_mic_raw": round(peak_mic, 2),
    }

    return CaptureAggregationResult(
        summarized_values=summarized_values,
        window_summary=window_summary,
        audio_summary=audio_summary,
        normalized_samples=normalized_samples,
    )
