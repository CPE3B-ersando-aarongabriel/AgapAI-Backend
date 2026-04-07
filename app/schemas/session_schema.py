from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class SessionStartRequest(BaseModel):
	device_id: str = Field(..., min_length=3, max_length=64)
	firmware_version: str | None = Field(default=None, max_length=32)
	metadata: dict[str, Any] = Field(default_factory=dict)


class SessionStartResponse(BaseModel):
	session_id: str
	device_id: str
	status: Literal["started"]
	started_at: datetime


class SessionChunkSampleIn(BaseModel):
	recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
	mic_raw: float = Field(..., ge=0.0)
	mic_rms: float = Field(..., ge=0.0)
	mic_peak: float = Field(..., ge=0.0)
	temperature: float = Field(..., ge=5.0, le=45.0)
	humidity: float = Field(..., ge=0.0, le=100.0)
	breathing_rate: float = Field(..., ge=0.0, le=60.0)
	movement_level: float = Field(..., ge=0.0, le=100.0)
	presence_detected: bool


class SessionChunkRequest(BaseModel):
	session_id: str = Field(..., min_length=8, max_length=64)
	chunk_id: str | None = Field(default=None, max_length=64)
	samples: list[SessionChunkSampleIn] = Field(..., min_length=1, max_length=25)


class SessionChunkResponse(BaseModel):
	session_id: str
	status: Literal["chunk_received"]
	received_count: int = Field(..., ge=1)
	total_samples: int = Field(..., ge=1)
	last_recorded_at: datetime


class SessionSummaryMetrics(BaseModel):
	sample_count: int = Field(..., ge=1)
	average_amplitude: float = Field(..., ge=0.0)
	rms_amplitude: float = Field(..., ge=0.0)
	peak_intensity: float = Field(..., ge=0.0)
	snore_event_count: int = Field(..., ge=0)
	snore_score: float = Field(..., ge=0.0, le=100.0)
	average_breathing_rate: float = Field(..., ge=0.0, le=60.0)
	average_temperature: float = Field(..., ge=5.0, le=45.0)
	average_humidity: float = Field(..., ge=0.0, le=100.0)


class SessionEndRequest(BaseModel):
	session_id: str = Field(..., min_length=8, max_length=64)
	ended_at: datetime | None = None
	summary: SessionSummaryMetrics


class SessionEndResponse(BaseModel):
	session_id: str
	status: Literal["ended"]
	ended_at: datetime
	final_summary: SessionSummaryMetrics
	recommendations: list[str] = Field(..., min_length=3, max_length=3)
	breathing_pattern: BreathingPatternGuide
	pre_analysis: RuleBasedSummary
	ai_used: bool = False


class SessionLiveStatusResponse(BaseModel):
	session_id: str
	device_id: str
	status: str
	started_at: datetime
	updated_at: datetime
	last_sample_at: datetime | None = None
	sample_count: int = Field(..., ge=0)
	average_amplitude: float = Field(..., ge=0.0)
	rms_amplitude: float = Field(..., ge=0.0)
	peak_intensity: float = Field(..., ge=0.0)
	snore_event_count: int = Field(..., ge=0)
	average_breathing_rate: float = Field(..., ge=0.0, le=60.0)
	average_temperature: float = Field(..., ge=0.0)
	average_humidity: float = Field(..., ge=0.0)


class SessionSummaryResponse(BaseModel):
	session_id: str
	device_id: str
	status: str
	started_at: datetime
	updated_at: datetime
	ended_at: datetime | None = None
	sample_count: int = Field(default=0, ge=0)
	device_summary: SessionSummaryMetrics | None = None
	backend_summary: SessionSummaryMetrics | None = None
	final_summary: SessionSummaryMetrics | None = None
	latest_pre_analysis: dict[str, Any] | None = None
	latest_device_response: dict[str, Any] | None = None


class DeviceSessionHistoryResponse(BaseModel):
	device_id: str
	total: int
	sessions: list[SessionSummaryResponse]


class SessionSampleRecord(BaseModel):
	recorded_at: datetime
	mic_raw: float = Field(..., ge=0.0)
	mic_rms: float = Field(..., ge=0.0)
	mic_peak: float = Field(..., ge=0.0)
	temperature: float = Field(..., ge=0.0)
	humidity: float = Field(..., ge=0.0, le=100.0)
	breathing_rate: float = Field(..., ge=0.0, le=60.0)
	movement_level: float = Field(..., ge=0.0, le=100.0)
	presence_detected: bool
	received_at: datetime
	chunk_id: str | None = None


class SessionSamplesPageResponse(BaseModel):
	session_id: str
	total: int
	samples: list[SessionSampleRecord]


class CaptureSampleIn(BaseModel):
	recorded_at: datetime
	mic_raw: float = Field(..., ge=0.0)
	mic_rms: float | None = Field(default=None, ge=0.0)
	mic_peak: float | None = Field(default=None, ge=0.0)
	temperature: float = Field(..., ge=5.0, le=45.0)
	humidity: float = Field(..., ge=0.0, le=100.0)
	breathing_rate: float | None = Field(default=None, ge=0.0, le=60.0)
	movement_level: float | None = Field(default=None, ge=0.0, le=100.0)
	presence_detected: bool | None = None


class CaptureWindowSummary(BaseModel):
	sample_count: int = Field(..., ge=1)
	window_started_at: datetime
	window_ended_at: datetime
	avg_mic_raw: float = Field(..., ge=0.0)
	max_mic_raw: float = Field(..., ge=0.0)


class AudioSummaryIn(BaseModel):
	sample_count: int = Field(..., ge=1)
	average_amplitude: float = Field(..., ge=0.0)
	rms_amplitude: float = Field(..., ge=0.0)
	peak_intensity: float = Field(..., ge=0.0)
	snore_event_count: int = Field(..., ge=0)
	snore_score: float = Field(..., ge=0.0, le=100.0)


class SensorDataIn(BaseModel):
	session_id: str = Field(..., min_length=8, max_length=64)
	breathing_rate: float | None = Field(default=None, ge=0.0, le=60.0)
	snore_level: float | None = Field(default=None, ge=0.0, le=100.0)
	temperature: float | None = Field(default=None, ge=5.0, le=45.0)
	humidity: float | None = Field(default=None, ge=0.0, le=100.0)
	movement_level: float | None = Field(default=None, ge=0.0, le=100.0)
	presence_detected: bool | None = None
	mic_raw: float | None = Field(default=None, ge=0.0)
	audio_summary: AudioSummaryIn | None = None
	capture_samples: list[CaptureSampleIn] = Field(default_factory=list)
	recorded_at: datetime | None = None

	@model_validator(mode="after")
	def validate_sensor_or_capture_payload(self) -> "SensorDataIn":
		has_capture_samples = len(self.capture_samples) > 0
		has_scalar_summary = all(
			value is not None
			for value in (self.breathing_rate, self.snore_level, self.temperature, self.humidity)
		)

		if not has_capture_samples and not has_scalar_summary:
			raise ValueError(
				"Provide either scalar summary values (breathing_rate/snore_level/temperature/humidity) "
				"or a non-empty capture_samples list."
			)
		return self


class BreathingPatternGuide(BaseModel):
	label: str
	inhale_seconds: int = Field(..., ge=2, le=8)
	hold_seconds: int = Field(..., ge=0, le=8)
	exhale_seconds: int = Field(..., ge=2, le=10)
	cycles: int = Field(..., ge=1, le=20)


class RuleBasedSummary(BaseModel):
	risk_level: Literal["low", "moderate", "high"]
	flags: list[str] = Field(default_factory=list)
	summary: str


class DeviceDataResponse(BaseModel):
	session_id: str
	recommendations: list[str] = Field(..., min_length=3, max_length=3)
	breathing_pattern: BreathingPatternGuide
	pre_analysis: RuleBasedSummary
	ai_used: bool = False
	capture_window_summary: CaptureWindowSummary | None = None
	audio_summary: AudioSummaryIn | None = None


class SessionRecordResponse(BaseModel):
	session_id: str
	device_id: str
	started_at: datetime
	updated_at: datetime
	ended_at: datetime | None = None
	sensor_events: list[dict[str, Any]] = Field(default_factory=list)
	latest_pre_analysis: dict[str, Any] | None = None
	latest_device_response: dict[str, Any] | None = None
	advanced_analysis: dict[str, Any] | None = None
	insight_history: list[dict[str, Any]] = Field(default_factory=list)


class SessionHistoryResponse(BaseModel):
	sessions: list[SessionRecordResponse]
	total: int


class AdvancedAnalysisRequest(BaseModel):
	focus_areas: list[str] = Field(default_factory=list)
	include_environmental_context: bool = True
	include_behavioral_suggestions: bool = True


class AdvancedAnalysisResponse(BaseModel):
	session_id: str
	detailed_insights: list[str]
	recommendations: list[str]
	confidence_note: str
	generated_at: datetime
	ai_used: bool


class DashboardTrendPoint(BaseModel):
	date: str
	avg_breathing_rate: float
	avg_snore_level: float


class DashboardLatestHighlight(BaseModel):
	session_id: str
	device_id: str
	updated_at: datetime
	summary: str


class DashboardResponse(BaseModel):
	total_sessions: int
	average_breathing_rate: float
	average_snore_level: float
	latest_highlights: list[DashboardLatestHighlight]
	trends: list[DashboardTrendPoint]


class ErrorResponse(BaseModel):
	error: str
	detail: str
	code: int
	timestamp: datetime


class SessionListQuery(BaseModel):
	limit: int = Field(default=20, ge=1, le=100)
	skip: int = Field(default=0, ge=0)
	device_id: str | None = None

	@model_validator(mode="after")
	def validate_device_id(self) -> "SessionListQuery":
		if self.device_id is not None and not self.device_id.strip():
			self.device_id = None
		return self
