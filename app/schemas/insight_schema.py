from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class InsightChatRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=1200)
    session_id: str | None = Field(default=None, min_length=8, max_length=64)
    device_id: str | None = Field(default=None, min_length=3, max_length=64)
    store_conversation: bool = False

    @model_validator(mode="after")
    def validate_filters(self) -> "InsightChatRequest":
        if self.session_id is not None and not self.session_id.strip():
            self.session_id = None
        if self.device_id is not None and not self.device_id.strip():
            self.device_id = None
        return self


class InsightDataContext(BaseModel):
    mode: Literal["generic", "device", "session"]
    device_id: str | None = None
    session_id: str | None = None
    latest_session_id: str | None = None
    sessions_considered: int = Field(default=0, ge=0)
    has_pre_analysis: bool = False
    has_advanced_analysis: bool = False
    has_dashboard_context: bool = False


class InsightChatResponse(BaseModel):
    question: str
    answer: str
    context: InsightDataContext
    ai_used: bool
    grounded: bool = True
    generated_at: datetime
