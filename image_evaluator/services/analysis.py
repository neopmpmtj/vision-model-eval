"""Shared analysis result DTO for all model labs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class AnalysisResult:
    response_text: str
    request_started_at: datetime
    request_finished_at: datetime
    latency_wall_seconds: float
    latency_openai_seconds: float | None
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    reasoning_tokens: int | None
    cached_tokens: int | None
    cache_write_tokens: int | None
    usage_raw: dict[str, Any]
    api_request: dict[str, Any]
    api_response: dict[str, Any]
    openai_response_id: str
    response_model: str
    openai_status: str
    time_to_first_token_seconds: float | None = None

    @property
    def latency_seconds(self) -> float:
        return self.latency_wall_seconds
