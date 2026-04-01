from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from app.core.constants import (
    BREATHING_RATE_HIGH,
    BREATHING_RATE_LOW,
    HUMIDITY_HIGH,
    HUMIDITY_LOW,
    MAX_RECOMMENDATIONS,
    SNORE_LEVEL_HIGH,
    SNORE_LEVEL_MILD,
    TEMPERATURE_HIGH,
    TEMPERATURE_LOW,
)
from app.core.settings import get_settings
from app.utils.helpers import ensure_three_recommendations


class AnalysisService:
    def __init__(self):
        self.settings = get_settings()
        self._client: OpenAI | None = None
        if self.settings.openai_api_key:
            self._client = OpenAI(api_key=self.settings.openai_api_key)

    def pre_analyze(self, payload: dict[str, Any]) -> dict[str, Any]:
        flags: list[str] = []
        summary_parts: list[str] = []

        breathing_rate = float(payload["breathing_rate"])
        snore_level = float(payload["snore_level"])
        temperature = float(payload["temperature"])
        humidity = float(payload["humidity"])

        if breathing_rate < BREATHING_RATE_LOW:
            flags.append("low_breathing_rate")
            summary_parts.append("Breathing is slower than expected.")
        elif breathing_rate > BREATHING_RATE_HIGH:
            flags.append("high_breathing_rate")
            summary_parts.append("Breathing is elevated and may be irregular.")

        if snore_level >= SNORE_LEVEL_HIGH:
            flags.append("high_snore")
            summary_parts.append("Snoring intensity is high.")
        elif snore_level >= SNORE_LEVEL_MILD:
            flags.append("mild_snore")
            summary_parts.append("Mild snoring detected.")

        if temperature < TEMPERATURE_LOW:
            flags.append("low_temperature")
            summary_parts.append("Room temperature is on the cooler side.")
        elif temperature > TEMPERATURE_HIGH:
            flags.append("high_temperature")
            summary_parts.append("Room temperature is warm for optimal sleep.")

        if humidity < HUMIDITY_LOW:
            flags.append("low_humidity")
            summary_parts.append("Room air is dry.")
        elif humidity > HUMIDITY_HIGH:
            flags.append("high_humidity")
            summary_parts.append("Room humidity is elevated.")

        risk_level = "low"
        if len(flags) >= 4 or "high_snore" in flags:
            risk_level = "high"
        elif len(flags) >= 2:
            risk_level = "moderate"

        if not summary_parts:
            summary_parts.append("Sleep conditions look stable in this sample.")

        return {
            "risk_level": risk_level,
            "flags": flags,
            "summary": " ".join(summary_parts),
        }

    def build_breathing_pattern(self, pre_analysis: dict[str, Any]) -> dict[str, Any]:
        risk_level = pre_analysis.get("risk_level", "low")
        if risk_level == "high":
            return {
                "label": "Calming 4-2-6",
                "inhale_seconds": 4,
                "hold_seconds": 2,
                "exhale_seconds": 6,
                "cycles": 10,
            }
        if risk_level == "moderate":
            return {
                "label": "Balanced 4-1-5",
                "inhale_seconds": 4,
                "hold_seconds": 1,
                "exhale_seconds": 5,
                "cycles": 8,
            }
        return {
            "label": "Light 4-0-4",
            "inhale_seconds": 4,
            "hold_seconds": 0,
            "exhale_seconds": 4,
            "cycles": 6,
        }

    def build_rule_recommendations(self, payload: dict[str, Any], pre_analysis: dict[str, Any]) -> list[str]:
        recommendations: list[str] = []

        if "high_breathing_rate" in pre_analysis["flags"]:
            recommendations.append("Slow down breathing to a steady nasal rhythm.")
        if "high_snore" in pre_analysis["flags"]:
            recommendations.append("Shift sleeping posture to reduce airway resistance.")
        if "high_temperature" in pre_analysis["flags"]:
            recommendations.append("Lower room temperature slightly for deeper sleep.")
        if "high_humidity" in pre_analysis["flags"]:
            recommendations.append("Improve room airflow to balance humidity.")
        if "low_humidity" in pre_analysis["flags"]:
            recommendations.append("Increase moisture in the room to ease breathing.")

        if not recommendations:
            recommendations = [
                "Maintain this stable breathing rhythm for 5 minutes.",
                "Keep the room calm and low-noise.",
                "Use consistent bedtime breathing practice.",
            ]

        return ensure_three_recommendations(recommendations)

    def ai_concise_recommendations(
        self,
        payload: dict[str, Any],
        pre_analysis: dict[str, Any],
    ) -> tuple[list[str], bool]:
        if not self.settings.enable_ai_pre_analysis or not self._client:
            return [], False

        prompt = (
            "You are an AI breath-pattern sleep coach for an embedded device. "
            "Return JSON with this exact shape: "
            "{\"recommendations\": [\"...\", \"...\", \"...\"], "
            "\"note\": \"one concise sentence\"}. "
            "Each recommendation must be short (<= 10 words), practical, and device-friendly. "
            "Focus on breathing irregularities, snoring patterns, room temperature/humidity, and sleep comfort. "
            f"Sensor sample: {json.dumps(payload, default=str)}. "
            f"Pre-analysis: {json.dumps(pre_analysis, default=str)}"
        )

        try:
            response = self._client.responses.create(
                model=self.settings.openai_model,
                input=prompt,
                max_output_tokens=220,
            )
            content = (response.output_text or "").strip()
            parsed = json.loads(content)
            recommendations = parsed.get("recommendations", [])
            if not isinstance(recommendations, list):
                return [], False
            return ensure_three_recommendations([str(item) for item in recommendations])[:MAX_RECOMMENDATIONS], True
        except Exception:
            return [], False

    def advanced_analysis(
        self,
        session_doc: dict[str, Any],
        focus_areas: list[str],
        include_environmental_context: bool,
        include_behavioral_suggestions: bool,
    ) -> tuple[dict[str, Any], bool]:
        sensor_events = session_doc.get("sensor_events", [])
        if not sensor_events:
            payload = {
                "detailed_insights": ["No sensor data available yet for advanced analysis."],
                "recommendations": [
                    "Collect at least 5 minutes of session data first.",
                    "Ensure sensor placement is stable near the sleeper.",
                    "Re-run advanced analysis after more samples.",
                ],
                "confidence_note": "Insufficient data for a robust interpretation.",
            }
            return payload, False

        if self._client:
            prompt = (
                "You are an expert sleep coach analyzing sensor time series from an ESP32 bedside device. "
                "Return JSON with keys: detailed_insights (array of 3-6 strings), "
                "recommendations (array of exactly 3 short actions), confidence_note (string). "
                "Focus on breathing trends, snore trend, environmental impacts, and actionable advice. "
                "Avoid medical diagnosis claims. "
                f"Session data: {json.dumps(sensor_events, default=str)}. "
                f"Focus areas: {focus_areas}. "
                f"Include environmental context: {include_environmental_context}. "
                f"Include behavioral suggestions: {include_behavioral_suggestions}."
            )
            try:
                response = self._client.responses.create(
                    model=self.settings.openai_model,
                    input=prompt,
                    max_output_tokens=600,
                )
                content = (response.output_text or "").strip()
                parsed = json.loads(content)
                parsed["recommendations"] = ensure_three_recommendations(
                    [str(item) for item in parsed.get("recommendations", [])]
                )
                if not parsed.get("detailed_insights"):
                    parsed["detailed_insights"] = ["Pattern summary could not be extracted clearly."]
                if not parsed.get("confidence_note"):
                    parsed["confidence_note"] = "AI-assisted analysis generated from available session data."
                return parsed, True
            except Exception:
                pass

        avg_br = sum(float(e.get("breathing_rate", 0.0)) for e in sensor_events) / max(len(sensor_events), 1)
        avg_sn = sum(float(e.get("snore_level", 0.0)) for e in sensor_events) / max(len(sensor_events), 1)
        avg_temp = sum(float(e.get("temperature", 0.0)) for e in sensor_events) / max(len(sensor_events), 1)
        avg_hum = sum(float(e.get("humidity", 0.0)) for e in sensor_events) / max(len(sensor_events), 1)

        insights = [
            f"Average breathing rate during session: {avg_br:.1f} bpm.",
            f"Average snore level during session: {avg_sn:.1f}/100.",
            f"Room conditions averaged {avg_temp:.1f}C and {avg_hum:.1f}% humidity.",
        ]
        if include_behavioral_suggestions:
            insights.append("Consistent pre-sleep breathing practice may improve stability.")

        recommendations = ensure_three_recommendations(
            [
                "Keep a steady exhale-focused breathing rhythm before sleep.",
                "Optimize sleeping posture when snore level rises.",
                "Target a cooler room and moderate humidity overnight.",
            ]
        )
        payload = {
            "detailed_insights": insights,
            "recommendations": recommendations,
            "confidence_note": "Rule-based advanced analysis used due to unavailable AI response.",
        }
        return payload, False
