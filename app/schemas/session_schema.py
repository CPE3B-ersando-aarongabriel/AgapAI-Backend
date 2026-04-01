from __future__ import annotations

from datetime import datetime
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


class SensorDataIn(BaseModel):
	session_id: str = Field(..., min_length=8, max_length=64)
	breathing_rate: float = Field(..., ge=0.0, le=60.0)
	snore_level: float = Field(..., ge=0.0, le=100.0)
	temperature: float = Field(..., ge=5.0, le=45.0)
	humidity: float = Field(..., ge=0.0, le=100.0)
	movement_level: float | None = Field(default=None, ge=0.0, le=100.0)
	presence_detected: bool | None = None
	recorded_at: datetime | None = None


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
