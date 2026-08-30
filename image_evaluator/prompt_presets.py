"""Eval prompt preset catalog helpers."""

from __future__ import annotations

from django.conf import settings

CUSTOM_PRESET_ID = "custom"


def preset_catalog() -> dict[str, dict[str, str]]:
    return dict(settings.EVAL_PROMPT_PRESETS)


def preset_choices() -> list[tuple[str, str]]:
    choices = [
        (preset_id, preset["label"])
        for preset_id, preset in settings.EVAL_PROMPT_PRESETS.items()
    ]
    choices.append((CUSTOM_PRESET_ID, "Custom"))
    return choices


def preset_texts() -> dict[str, str]:
    return {
        preset_id: preset["text"]
        for preset_id, preset in settings.EVAL_PROMPT_PRESETS.items()
    }


def default_preset_id() -> str:
    return settings.EVAL_PROMPT_DEFAULT_ID


def default_prompt_text() -> str:
    preset = settings.EVAL_PROMPT_PRESETS.get(settings.EVAL_PROMPT_DEFAULT_ID, {})
    return preset.get("text") or settings.DEFAULT_EVAL_PROMPT
