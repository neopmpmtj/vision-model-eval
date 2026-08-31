"""Shared API key status types and OpenAI re-exports."""

from __future__ import annotations

from dataclasses import dataclass, field

from openai import RateLimitError

# 1x1 red PNG
PROBE_IMAGE_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
PROBE_PROMPT = "Reply with exactly: ok"


@dataclass(frozen=True)
class ApiKeyStatus:
    ok: bool
    message: str
    missing_models: list[str] = field(default_factory=list)
    checked_models: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ProbeStatus:
    ok: bool
    message: str
    model: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None


def _is_insufficient_quota(exc: RateLimitError) -> bool:
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error = body.get("error", {})
        if isinstance(error, dict) and error.get("code") == "insufficient_quota":
            return True
    message = str(exc).lower()
    return "insufficient_quota" in message or "insufficient quota" in message


def _is_billing_or_quota_error(exc: Exception) -> bool:
    if isinstance(exc, RateLimitError) and _is_insufficient_quota(exc):
        return True
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error = body.get("error", {})
        if isinstance(error, dict):
            code = str(error.get("code", "")).lower()
            if code in ("insufficient_quota", "resource_exhausted", "insufficient_credits"):
                return True
    message = str(exc).lower()
    markers = (
        "insufficient_quota",
        "insufficient quota",
        "insufficient_credits",
        "insufficient credits",
        "resource_exhausted",
        "resource exhausted",
        "exceeded your current quota",
        "quota exceeded",
        "billing",
        "payment required",
        "out of credits",
    )
    return any(marker in message for marker in markers)


def _insufficient_quota_probe_message(lab_label: str) -> str:
    return (
        f"Billable probe failed: insufficient quota or credits. "
        f"Add credits or check billing limits in your {lab_label} account."
    )


from .lab_api_key import run_openai_billable_probe as run_billable_probe
from .lab_api_key import validate_openai_api_key as validate_api_key

__all__ = [
    "ApiKeyStatus",
    "PROBE_IMAGE_DATA_URL",
    "PROBE_PROMPT",
    "ProbeStatus",
    "run_billable_probe",
    "validate_api_key",
]
