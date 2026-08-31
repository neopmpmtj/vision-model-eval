"""Google Gemini vision evaluation helpers."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from django.conf import settings
from google import genai
from google.genai import types

from .analysis import AnalysisResult

# google.genai.types.ThinkingConfig.thinking_level (Gemini 3.x)
THINKING_LEVEL_CHOICES = ("minimal", "low", "medium", "high")

# Form/UI values map to google.genai.types.MediaResolution
MEDIA_RESOLUTION_MAP = {
    "low": types.MediaResolution.MEDIA_RESOLUTION_LOW,
    "medium": types.MediaResolution.MEDIA_RESOLUTION_MEDIUM,
    "high": types.MediaResolution.MEDIA_RESOLUTION_HIGH,
}


@dataclass(frozen=True)
class GeminiApiRequestConfig:
    thinking_level: str
    thinking_budget: int
    media_resolution: str
    max_output_tokens: int

    @classmethod
    def from_settings(cls) -> GeminiApiRequestConfig:
        return cls(
            thinking_level=settings.GEMINI_DEFAULT_THINKING_LEVEL,
            thinking_budget=settings.GEMINI_DEFAULT_THINKING_BUDGET,
            media_resolution=settings.GEMINI_DEFAULT_MEDIA_RESOLUTION,
            max_output_tokens=settings.GEMINI_DEFAULT_MAX_OUTPUT_TOKENS,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> GeminiApiRequestConfig:
        if not data:
            return cls.from_settings()
        return cls(
            thinking_level=str(data.get("thinking_level") or settings.GEMINI_DEFAULT_THINKING_LEVEL),
            thinking_budget=int(data.get("thinking_budget", settings.GEMINI_DEFAULT_THINKING_BUDGET)),
            media_resolution=str(data.get("media_resolution") or settings.GEMINI_DEFAULT_MEDIA_RESOLUTION),
            max_output_tokens=int(data.get("max_output_tokens") or settings.GEMINI_DEFAULT_MAX_OUTPUT_TOKENS),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "thinking_level": self.thinking_level,
            "thinking_budget": self.thinking_budget,
            "media_resolution": self.media_resolution,
            "max_output_tokens": self.max_output_tokens,
        }


def _thinking_config_for_model(*, model: str, config: GeminiApiRequestConfig) -> types.ThinkingConfig | None:
    if model.startswith("gemini-3"):
        return types.ThinkingConfig(thinking_level=config.thinking_level)
    if model.startswith("gemini-2.5-"):
        return types.ThinkingConfig(thinking_budget=config.thinking_budget)
    return None


def _media_resolution(config: GeminiApiRequestConfig) -> types.MediaResolution:
    return MEDIA_RESOLUTION_MAP.get(config.media_resolution, types.MediaResolution.MEDIA_RESOLUTION_HIGH)


def _usage_value(usage: Any, *keys: str) -> int | None:
    if usage is None:
        return None
    for key in keys:
        if hasattr(usage, key):
            value = getattr(usage, key)
            if value is not None:
                return int(value)
    return None


def _response_snapshot(response: Any, *, model: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    if hasattr(response, "model_dump"):
        data = response.model_dump(mode="json", exclude_none=True)
    return {
        "id": data.get("response_id") or getattr(response, "response_id", "") or "",
        "model": str(getattr(response, "model_version", None) or model),
        "status": str(data.get("status") or "completed"),
        "usage": data.get("usage_metadata"),
    }


def analyze_image(
    *,
    model: str,
    instructions: str = "",
    user_prompt: str = "",
    image_path: Path | str,
    image_content_type: str = "image/jpeg",
    api_config: GeminiApiRequestConfig | None = None,
) -> AnalysisResult:
    config = api_config or GeminiApiRequestConfig.from_settings()
    image_bytes = Path(image_path).read_bytes()
    instructions_text = instructions.strip()
    user_text = user_prompt.strip()

    parts: list[types.Part] = []
    if user_text:
        parts.append(types.Part.from_text(text=user_text))
    parts.append(types.Part.from_bytes(data=image_bytes, mime_type=image_content_type))

    thinking_config = _thinking_config_for_model(model=model, config=config)
    generate_config = types.GenerateContentConfig(
        max_output_tokens=config.max_output_tokens,
        media_resolution=_media_resolution(config),
    )
    if instructions_text:
        generate_config.system_instruction = instructions_text
    if thinking_config is not None:
        generate_config.thinking_config = thinking_config

    api_request = {
        "model": model,
        "instructions": instructions_text,
        "user_prompt": user_text,
        **config.to_dict(),
        "thinking_sent": (
            {"thinking_level": config.thinking_level}
            if model.startswith("gemini-3")
            else {"thinking_budget": config.thinking_budget}
            if model.startswith("gemini-2.5-")
            else None
        ),
    }

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    request_started_at = datetime.now(timezone.utc)
    started_perf = time.perf_counter()
    response = client.models.generate_content(
        model=model,
        contents=parts,
        config=generate_config,
    )
    request_finished_at = datetime.now(timezone.utc)
    latency_wall_seconds = round(time.perf_counter() - started_perf, 3)

    usage = getattr(response, "usage_metadata", None)
    usage_raw: dict[str, Any] = {}
    if usage is not None and hasattr(usage, "model_dump"):
        usage_raw = usage.model_dump(mode="json")

    response_text = getattr(response, "text", None) or ""
    return AnalysisResult(
        response_text=response_text,
        request_started_at=request_started_at,
        request_finished_at=request_finished_at,
        latency_wall_seconds=latency_wall_seconds,
        latency_openai_seconds=None,
        input_tokens=_usage_value(usage, "prompt_token_count"),
        output_tokens=_usage_value(usage, "candidates_token_count"),
        total_tokens=_usage_value(usage, "total_token_count"),
        reasoning_tokens=_usage_value(usage, "thoughts_token_count"),
        cached_tokens=_usage_value(usage, "cached_content_token_count"),
        cache_write_tokens=None,
        usage_raw=usage_raw,
        api_request=api_request,
        api_response=_response_snapshot(response, model=model),
        openai_response_id=str(getattr(response, "response_id", "") or ""),
        response_model=str(getattr(response, "model_version", None) or model),
        openai_status="completed",
    )
