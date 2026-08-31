"""DeepSeek vision evaluation helpers."""

from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from django.conf import settings
from openai import OpenAI

from .analysis import AnalysisResult

DEEPSEEK_BASE_URL = "https://api.deepseek.com"

# api-docs.deepseek.com Chat Completions reasoning_effort
DEEPSEEK_REASONING_EFFORT_CHOICES = ("none", "low", "high", "max")

# api-docs.deepseek.com/guides/vision detail
DEEPSEEK_IMAGE_DETAIL_CHOICES = ("auto", "low", "high", "original")


@dataclass(frozen=True)
class DeepSeekApiRequestConfig:
    reasoning_effort: str
    max_output_tokens: int
    image_detail: str

    @classmethod
    def from_settings(cls) -> DeepSeekApiRequestConfig:
        return cls(
            reasoning_effort=settings.DEEPSEEK_DEFAULT_REASONING_EFFORT,
            max_output_tokens=settings.DEEPSEEK_DEFAULT_MAX_OUTPUT_TOKENS,
            image_detail=settings.DEEPSEEK_DEFAULT_IMAGE_DETAIL,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> DeepSeekApiRequestConfig:
        if not data:
            return cls.from_settings()
        reasoning = data.get("reasoning") if isinstance(data.get("reasoning"), dict) else {}
        effort = reasoning.get("effort") or data.get("reasoning_effort")
        return cls(
            reasoning_effort=str(effort or settings.DEEPSEEK_DEFAULT_REASONING_EFFORT),
            max_output_tokens=int(data.get("max_output_tokens") or settings.DEEPSEEK_DEFAULT_MAX_OUTPUT_TOKENS),
            image_detail=str(data.get("image_detail") or settings.DEEPSEEK_DEFAULT_IMAGE_DETAIL),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "reasoning": {"effort": self.reasoning_effort},
            "max_output_tokens": self.max_output_tokens,
            "image_detail": self.image_detail,
        }


def _client(api_key: str | None = None) -> OpenAI:
    key = api_key if api_key is not None else settings.DEEPSEEK_API_KEY
    return OpenAI(api_key=key, base_url=DEEPSEEK_BASE_URL)


def _usage_value(usage: Any, attr: str, nested_attr: str | None = None) -> int | None:
    if usage is None:
        return None
    if nested_attr:
        nested = getattr(usage, attr, None)
        if nested is None:
            return None
        return getattr(nested, nested_attr, None)
    return getattr(usage, attr, None)


def _response_snapshot(response: Any) -> dict[str, Any]:
    if hasattr(response, "model_dump"):
        data = response.model_dump(mode="json", exclude_none=True)
    else:
        data = {}
    return {
        "id": getattr(response, "id", ""),
        "model": str(getattr(response, "model", "")),
        "status": str(getattr(response, "status", "") or ""),
        "created_at": getattr(response, "created_at", None),
        "completed_at": getattr(response, "completed_at", None),
        "usage": data.get("usage"),
    }


def _openai_latency_seconds(response: Any) -> float | None:
    created_at = getattr(response, "created_at", None)
    completed_at = getattr(response, "completed_at", None)
    if created_at is None or completed_at is None:
        return None
    return round(float(completed_at) - float(created_at), 3)


def analyze_image(
    *,
    model: str,
    instructions: str = "",
    user_prompt: str = "",
    image_path: Path | str,
    image_content_type: str = "image/jpeg",
    api_config: DeepSeekApiRequestConfig | None = None,
) -> AnalysisResult:
    config = api_config or DeepSeekApiRequestConfig.from_settings()
    image_bytes = Path(image_path).read_bytes()
    encoded_image = base64.b64encode(image_bytes).decode("utf-8")
    image_data_url = f"data:{image_content_type};base64,{encoded_image}"
    instructions_text = instructions.strip()
    user_text = user_prompt.strip()

    content: list[dict[str, Any]] = []
    if user_text:
        content.append({"type": "input_text", "text": user_text})
    content.append(
        {
            "type": "input_image",
            "image_url": image_data_url,
            "detail": config.image_detail,
        }
    )

    api_request = {
        "model": model,
        "instructions": instructions_text,
        "user_prompt": user_text,
        **config.to_dict(),
    }

    create_kwargs: dict[str, Any] = {
        "model": model,
        "input": [
            {
                "role": "user",
                "content": content,
            }
        ],
        "reasoning": {"effort": config.reasoning_effort},
        "max_output_tokens": config.max_output_tokens,
    }
    if instructions_text:
        create_kwargs["instructions"] = instructions_text

    client = _client()
    request_started_at = datetime.now(timezone.utc)
    started_perf = time.perf_counter()
    response = client.responses.create(**create_kwargs)
    request_finished_at = datetime.now(timezone.utc)
    latency_wall_seconds = round(time.perf_counter() - started_perf, 3)
    usage = getattr(response, "usage", None)
    usage_raw: dict[str, Any] = {}
    if usage is not None and hasattr(usage, "model_dump"):
        usage_raw = usage.model_dump(mode="json")

    return AnalysisResult(
        response_text=response.output_text,
        request_started_at=request_started_at,
        request_finished_at=request_finished_at,
        latency_wall_seconds=latency_wall_seconds,
        latency_openai_seconds=_openai_latency_seconds(response),
        input_tokens=_usage_value(usage, "input_tokens"),
        output_tokens=_usage_value(usage, "output_tokens"),
        total_tokens=_usage_value(usage, "total_tokens"),
        reasoning_tokens=_usage_value(usage, "output_tokens_details", "reasoning_tokens"),
        cached_tokens=_usage_value(usage, "input_tokens_details", "cached_tokens"),
        cache_write_tokens=_usage_value(usage, "input_tokens_details", "cache_write_tokens"),
        usage_raw=usage_raw,
        api_request=api_request,
        api_response=_response_snapshot(response),
        openai_response_id=getattr(response, "id", "") or "",
        response_model=str(getattr(response, "model", "") or model),
        openai_status=str(getattr(response, "status", "") or ""),
    )
