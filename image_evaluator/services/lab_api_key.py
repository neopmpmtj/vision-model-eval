"""Per-lab API key validation."""

from __future__ import annotations

from dataclasses import dataclass, field

from django.conf import settings
from google import genai
from openai import APIConnectionError, AuthenticationError, OpenAI, PermissionDeniedError, RateLimitError

from image_evaluator.model_catalog import enabled_labs, lab_label, models_for_lab

from .api_key import (
    ApiKeyStatus,
    PROBE_IMAGE_DATA_URL,
    PROBE_PROMPT,
    ProbeStatus,
    _insufficient_quota_probe_message,
    _is_billing_or_quota_error,
    _is_insufficient_quota,
)

DEEPSEEK_BASE_URL = "https://api.deepseek.com"

LAB_KEY_SETTINGS = {
    "openai": "OPENAI_API_KEY",
    "google": "GEMINI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
}


def api_key_for_lab(lab_id: str) -> str:
    setting_name = LAB_KEY_SETTINGS.get(lab_id, "")
    return str(getattr(settings, setting_name, "") or "")


def session_key_for_lab(lab_id: str) -> str:
    return f"api_key_status_{lab_id}"


def validate_openai_api_key(api_key: str | None = None) -> ApiKeyStatus:
    key = (api_key if api_key is not None else settings.OPENAI_API_KEY) or ""
    if not key.strip():
        return ApiKeyStatus(ok=False, message="OPENAI_API_KEY is not set.")

    required_models = list(models_for_lab("openai"))
    try:
        client = OpenAI(api_key=key)
        available_ids = {model.id for model in client.models.list()}
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


def validate_gemini_api_key(api_key: str | None = None) -> ApiKeyStatus:
    key = (api_key if api_key is not None else settings.GEMINI_API_KEY) or ""
    if not key.strip():
        return ApiKeyStatus(ok=False, message="GEMINI_API_KEY is not set.")

    required_models = list(models_for_lab("google"))
    try:
        client = genai.Client(api_key=key)
        available_ids = {model.name.split("/")[-1] for model in client.models.list()}
    except Exception as exc:
        message = str(exc).lower()
        if "api key" in message or "permission" in message or "unauth" in message:
            return ApiKeyStatus(
                ok=False,
                message="GEMINI_API_KEY was rejected by Google (invalid or revoked).",
                checked_models=required_models,
            )
        return ApiKeyStatus(
            ok=False,
            message=f"Could not validate GEMINI_API_KEY: {exc}",
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


def validate_deepseek_api_key(api_key: str | None = None) -> ApiKeyStatus:
    key = (api_key if api_key is not None else settings.DEEPSEEK_API_KEY) or ""
    if not key.strip():
        return ApiKeyStatus(ok=False, message="DEEPSEEK_API_KEY is not set.")

    required_models = list(models_for_lab("deepseek"))
    try:
        client = OpenAI(api_key=key, base_url=DEEPSEEK_BASE_URL)
        available_ids = {model.id for model in client.models.list()}
    except AuthenticationError:
        return ApiKeyStatus(
            ok=False,
            message="DEEPSEEK_API_KEY was rejected by DeepSeek (invalid or revoked).",
            checked_models=required_models,
        )
    except PermissionDeniedError:
        return ApiKeyStatus(
            ok=False,
            message="DEEPSEEK_API_KEY is valid but lacks permission to list models.",
            checked_models=required_models,
        )
    except RateLimitError:
        return ApiKeyStatus(
            ok=False,
            message="DeepSeek rate limit reached while validating the API key. Try again shortly.",
            checked_models=required_models,
        )
    except APIConnectionError:
        return ApiKeyStatus(
            ok=False,
            message="Could not reach DeepSeek while validating the API key. Check your network.",
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


def validate_lab_api_key(lab_id: str, api_key: str | None = None) -> ApiKeyStatus:
    if lab_id == "google":
        return validate_gemini_api_key(api_key)
    if lab_id == "deepseek":
        return validate_deepseek_api_key(api_key)
    return validate_openai_api_key(api_key)


@dataclass(frozen=True)
class LabKeyContext:
    lab_id: str
    lab_label: str
    setting_name: str


def lab_key_context(lab_id: str) -> LabKeyContext:
    return LabKeyContext(
        lab_id=lab_id,
        lab_label=lab_label(lab_id),
        setting_name=LAB_KEY_SETTINGS.get(lab_id, "OPENAI_API_KEY"),
    )


def run_openai_billable_probe(*, model: str | None = None, api_key: str | None = None) -> ProbeStatus:
    key = (api_key if api_key is not None else settings.OPENAI_API_KEY) or ""
    if not key.strip():
        return ProbeStatus(ok=False, message="OPENAI_API_KEY is not set.")

    probe_model = model or models_for_lab("openai")[0]
    try:
        client = OpenAI(api_key=key)
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
                message=_insufficient_quota_probe_message("OpenAI"),
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


def run_gemini_billable_probe(*, model: str | None = None, api_key: str | None = None) -> ProbeStatus:
    from google.genai import types

    key = (api_key if api_key is not None else settings.GEMINI_API_KEY) or ""
    if not key.strip():
        return ProbeStatus(ok=False, message="GEMINI_API_KEY is not set.")

    probe_model = model or models_for_lab("google")[0]
    try:
        client = genai.Client(api_key=key)
        response = client.models.generate_content(
            model=probe_model,
            contents=[
                types.Part.from_text(text=PROBE_PROMPT),
                types.Part.from_bytes(
                    data=__import__("base64").b64decode(
                        PROBE_IMAGE_DATA_URL.split(",", 1)[1]
                    ),
                    mime_type="image/png",
                ),
            ],
            config=types.GenerateContentConfig(max_output_tokens=16),
        )
        usage = getattr(response, "usage_metadata", None)
        return ProbeStatus(
            ok=True,
            message="Billable vision probe succeeded.",
            model=probe_model,
            input_tokens=getattr(usage, "prompt_token_count", None),
            output_tokens=getattr(usage, "candidates_token_count", None),
        )
    except Exception as exc:
        if _is_billing_or_quota_error(exc):
            return ProbeStatus(
                ok=False,
                message=_insufficient_quota_probe_message("Google Gemini"),
                model=probe_model,
            )
        return ProbeStatus(
            ok=False,
            message=f"Billable probe failed: {exc}",
            model=probe_model,
        )


def run_deepseek_billable_probe(*, model: str | None = None, api_key: str | None = None) -> ProbeStatus:
    key = (api_key if api_key is not None else settings.DEEPSEEK_API_KEY) or ""
    if not key.strip():
        return ProbeStatus(ok=False, message="DEEPSEEK_API_KEY is not set.")

    probe_model = model or models_for_lab("deepseek")[0]
    try:
        client = OpenAI(api_key=key, base_url=DEEPSEEK_BASE_URL)
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
                message=_insufficient_quota_probe_message("DeepSeek"),
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
            message="Billable probe failed: could not reach DeepSeek. Check your network.",
            model=probe_model,
        )
    except Exception as exc:
        if _is_billing_or_quota_error(exc):
            return ProbeStatus(
                ok=False,
                message=_insufficient_quota_probe_message("DeepSeek"),
                model=probe_model,
            )
        return ProbeStatus(
            ok=False,
            message=f"Billable probe failed: {exc}",
            model=probe_model,
        )


def run_lab_billable_probe(*, lab_id: str, model: str | None = None, api_key: str | None = None) -> ProbeStatus:
    if lab_id == "google":
        return run_gemini_billable_probe(model=model, api_key=api_key)
    if lab_id == "deepseek":
        return run_deepseek_billable_probe(model=model, api_key=api_key)
    return run_openai_billable_probe(model=model, api_key=api_key)


def lab_key_alert(lab_id: str, *, request=None) -> dict:
    """Inline prepare-page status: missing key, invalid key, or ok."""
    context = lab_key_context(lab_id)
    key = api_key_for_lab(lab_id)
    if not key.strip():
        return {
            "lab_id": lab_id,
            "status": "missing",
            "ok": False,
            "setting_name": context.setting_name,
            "lab_label": context.lab_label,
            "headline": f"{context.setting_name} was not found",
            "message": (
                f"Add your {context.lab_label} key to the project root "
                f".env file as {context.setting_name}, then restart the server."
            ),
        }

    if request is not None:
        session_key = session_key_for_lab(lab_id)
        cached = request.session.get(session_key)
        if cached and cached.get("key") == key:
            status = ApiKeyStatus(
                ok=cached["ok"],
                message=cached["message"],
                missing_models=cached.get("missing_models", []),
                checked_models=cached.get("checked_models", []),
            )
        else:
            status = validate_lab_api_key(lab_id)
            request.session[session_key] = {
                "key": key,
                "ok": status.ok,
                "message": status.message,
                "missing_models": status.missing_models,
                "checked_models": status.checked_models,
            }
    else:
        status = validate_lab_api_key(lab_id)

    if not status.ok:
        alert = {
            "lab_id": lab_id,
            "status": "invalid",
            "ok": False,
            "setting_name": context.setting_name,
            "lab_label": context.lab_label,
            "headline": f"{context.lab_label} API key problem",
            "message": status.message,
        }
        if status.missing_models:
            alert["missing_models"] = status.missing_models
        return alert

    return {
        "lab_id": lab_id,
        "status": "ok",
        "ok": True,
        "setting_name": context.setting_name,
        "lab_label": context.lab_label,
    }


def lab_key_alerts_for_prepare(request) -> dict[str, dict]:
    return {lab_id: lab_key_alert(lab_id, request=request) for lab_id, _ in enabled_labs()}
