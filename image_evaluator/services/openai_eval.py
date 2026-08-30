"""OpenAI vision evaluation helpers."""

from __future__ import annotations

import base64
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from django.conf import settings
from openai import OpenAI


@dataclass(frozen=True)
class ApiRequestConfig:
    reasoning_effort: str
    max_output_tokens: int
    store: bool
    image_detail: str

    @classmethod
    def from_settings(cls) -> ApiRequestConfig:
        return cls(
            reasoning_effort=settings.OPENAI_DEFAULT_REASONING_EFFORT,
            max_output_tokens=settings.OPENAI_DEFAULT_MAX_OUTPUT_TOKENS,
            store=settings.OPENAI_DEFAULT_STORE,
            image_detail=settings.OPENAI_DEFAULT_IMAGE_DETAIL,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "reasoning": {"effort": self.reasoning_effort},
            "max_output_tokens": self.max_output_tokens,
            "store": self.store,
            "image_detail": self.image_detail,
        }


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


def default_api_defaults() -> dict[str, Any]:
    return ApiRequestConfig.from_settings().to_dict()


def shuffle_models(selected_models: list[str]) -> list[str]:
    model_order = list(selected_models)
    random.SystemRandom().shuffle(model_order)
    return model_order


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
        "max_output_tokens": getattr(response, "max_output_tokens", None),
        "reasoning": data.get("reasoning"),
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
    prompt: str,
    image_path: Path | str,
    image_content_type: str = "image/jpeg",
    api_config: ApiRequestConfig | None = None,
) -> AnalysisResult:
    config = api_config or ApiRequestConfig.from_settings()
    image_bytes = Path(image_path).read_bytes()
    encoded_image = base64.b64encode(image_bytes).decode("utf-8")
    image_data_url = f"data:{image_content_type};base64,{encoded_image}"

    api_request = {
        "model": model,
        "prompt": prompt,
        **config.to_dict(),
    }

    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    request_started_at = datetime.now(timezone.utc)
    started_perf = time.perf_counter()
    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {
                        "type": "input_image",
                        "image_url": image_data_url,
                        "detail": config.image_detail,
                    },
                ],
            }
        ],
        reasoning={"effort": config.reasoning_effort},
        max_output_tokens=config.max_output_tokens,
        store=config.store,
    )
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
