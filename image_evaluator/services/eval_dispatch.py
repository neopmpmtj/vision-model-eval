"""Route vision analysis to the correct lab module."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .analysis import AnalysisResult
from .deepseek_eval import DeepSeekApiRequestConfig, analyze_image as deepseek_analyze_image
from .gemini_eval import GeminiApiRequestConfig, analyze_image as gemini_analyze_image
from .openai_eval import ApiRequestConfig, analyze_image as openai_analyze_image


def analyze_image(
    *,
    lab: str,
    model: str,
    instructions: str = "",
    user_prompt: str = "",
    image_path: Path | str,
    image_content_type: str = "image/jpeg",
    api_defaults: dict[str, Any] | None = None,
) -> AnalysisResult:
    defaults = api_defaults or {}
    if lab == "google":
        return gemini_analyze_image(
            model=model,
            instructions=instructions,
            user_prompt=user_prompt,
            image_path=image_path,
            image_content_type=image_content_type,
            api_config=GeminiApiRequestConfig.from_dict(defaults),
        )
    if lab == "deepseek":
        return deepseek_analyze_image(
            model=model,
            instructions=instructions,
            user_prompt=user_prompt,
            image_path=image_path,
            image_content_type=image_content_type,
            api_config=DeepSeekApiRequestConfig.from_dict(defaults),
        )
    return openai_analyze_image(
        model=model,
        instructions=instructions,
        user_prompt=user_prompt,
        image_path=image_path,
        image_content_type=image_content_type,
        api_config=ApiRequestConfig.from_dict(defaults),
    )


def build_api_request_dict(
    *,
    lab: str,
    model: str,
    instructions: str = "",
    user_prompt: str = "",
    api_defaults: dict[str, Any] | None = None,
) -> dict[str, Any]:
    defaults = api_defaults or {}
    if lab == "google":
        config = GeminiApiRequestConfig.from_dict(defaults)
        return {
            "model": model,
            "instructions": instructions,
            "user_prompt": user_prompt,
            **config.to_dict(),
        }
    if lab == "deepseek":
        config = DeepSeekApiRequestConfig.from_dict(defaults)
        return {
            "model": model,
            "instructions": instructions,
            "user_prompt": user_prompt,
            **config.to_dict(),
        }
    config = ApiRequestConfig.from_dict(defaults)
    return {
        "model": model,
        "instructions": instructions,
        "user_prompt": user_prompt,
        **config.to_dict(),
    }
