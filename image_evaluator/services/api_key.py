"""OpenAI API key validation and minimal billable probe."""

from __future__ import annotations

from dataclasses import dataclass, field

from django.conf import settings
from openai import (
    APIConnectionError,
    AuthenticationError,
    OpenAI,
    PermissionDeniedError,
    RateLimitError,
)

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


def _client(api_key: str | None = None) -> OpenAI:
    key = api_key if api_key is not None else settings.OPENAI_API_KEY
    return OpenAI(api_key=key)


def _list_model_ids(client: OpenAI) -> set[str]:
    model_ids: set[str] = set()
    for model in client.models.list():
        model_ids.add(model.id)
    return model_ids


def validate_api_key(api_key: str | None = None) -> ApiKeyStatus:
    key = (api_key if api_key is not None else settings.OPENAI_API_KEY) or ""
    if not key.strip():
        return ApiKeyStatus(ok=False, message="OPENAI_API_KEY is not set.")

    required_models = list(settings.AVAILABLE_MODELS)
    try:
        client = _client(key)
        available_ids = _list_model_ids(client)
    except AuthenticationError:
        return ApiKeyStatus(
            ok=False,
            message="OPENAI_API_KEY was rejected by OpenAI (invalid or revoked).",
            checked_models=required_models,
        )
    except PermissionDeniedError:
        return ApiKeyStatus(
            ok=False,
            message="OPENAI_API_KEY is valid but lacks permission to list models.",
            checked_models=required_models,
        )
    except RateLimitError:
        return ApiKeyStatus(
            ok=False,
            message="OpenAI rate limit reached while validating the API key. Try again shortly.",
            checked_models=required_models,
        )
    except APIConnectionError:
        return ApiKeyStatus(
            ok=False,
            message="Could not reach OpenAI while validating the API key. Check your network.",
            checked_models=required_models,
        )
    except Exception as exc:
        return ApiKeyStatus(
            ok=False,
            message=f"Unexpected error while validating the API key: {exc}",
            checked_models=required_models,
        )

    missing_models = [model for model in required_models if model not in available_ids]
    if missing_models:
        return ApiKeyStatus(
            ok=False,
            message=(
                "API key is valid, but these configured models are not available on your account: "
                + ", ".join(missing_models)
            ),
            missing_models=missing_models,
            checked_models=required_models,
        )

    return ApiKeyStatus(
        ok=True,
        message="API key is valid and all configured models are listed.",
        checked_models=required_models,
    )


def _is_insufficient_quota(exc: RateLimitError) -> bool:
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error = body.get("error", {})
        if isinstance(error, dict) and error.get("code") == "insufficient_quota":
            return True
    message = str(exc).lower()
    return "insufficient_quota" in message or "insufficient quota" in message


def run_billable_probe(*, model: str | None = None, api_key: str | None = None) -> ProbeStatus:
    key = (api_key if api_key is not None else settings.OPENAI_API_KEY) or ""
    if not key.strip():
        return ProbeStatus(ok=False, message="OPENAI_API_KEY is not set.")

    probe_model = model or settings.AVAILABLE_MODELS[0]
    try:
        client = _client(key)
        response = client.responses.create(
            model=probe_model,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": PROBE_PROMPT},
                        {
                            "type": "input_image",
                            "image_url": PROBE_IMAGE_DATA_URL,
                            "detail": "low",
                        },
                    ],
                }
            ],
            reasoning={"effort": "low"},
            max_output_tokens=16,
            store=False,
        )
        usage = getattr(response, "usage", None)
        return ProbeStatus(
            ok=True,
            message="Billable vision probe succeeded.",
            model=probe_model,
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
        )
    except AuthenticationError:
        return ProbeStatus(
            ok=False,
            message="Billable probe failed: API key was rejected (invalid or revoked).",
            model=probe_model,
        )
    except PermissionDeniedError:
        return ProbeStatus(
            ok=False,
            message="Billable probe failed: API key lacks permission for this model or endpoint.",
            model=probe_model,
        )
    except RateLimitError as exc:
        if _is_insufficient_quota(exc):
            return ProbeStatus(
                ok=False,
                message=(
                    "Billable probe failed: insufficient quota. "
                    "Add credits or check billing limits in your OpenAI dashboard."
                ),
                model=probe_model,
            )
        return ProbeStatus(
            ok=False,
            message="Billable probe failed: rate limit reached. Try again shortly.",
            model=probe_model,
        )
    except APIConnectionError:
        return ProbeStatus(
            ok=False,
            message="Billable probe failed: could not reach OpenAI. Check your network.",
            model=probe_model,
        )
    except Exception as exc:
        return ProbeStatus(
            ok=False,
            message=f"Billable probe failed: {exc}",
            model=probe_model,
        )
