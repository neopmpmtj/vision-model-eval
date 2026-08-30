"""Eval system-instruction preset catalog helpers."""

from __future__ import annotations

from django.conf import settings


class ComposeEvalTextError(ValueError):
    """Invalid omit/preset/additional combination."""


def preset_catalog() -> dict[str, dict[str, str]]:
    return dict(settings.EVAL_PROMPT_PRESETS)


def preset_choices() -> list[tuple[str, str]]:
    return [
        (preset_id, preset["label"])
        for preset_id, preset in settings.EVAL_PROMPT_PRESETS.items()
    ]


def preset_texts() -> dict[str, str]:
    return {
        preset_id: preset["text"]
        for preset_id, preset in settings.EVAL_PROMPT_PRESETS.items()
    }


def default_preset_id() -> str:
    return settings.EVAL_PROMPT_DEFAULT_ID


def compose_eval_text(
    *,
    omit_instructions: bool,
    preset_id: str,
    additional: str,
) -> tuple[str, str]:
    """Return (instructions, user_prompt) for a session.

    When omit is true, additional is the user prompt and instructions are empty.
    When omit is false, instructions are the preset body plus optional additional;
    user_prompt is empty (image-only user content).
    """
    extra = additional.strip()
    if omit_instructions:
        if not extra:
            raise ComposeEvalTextError(
                "Enter additional instructions when system instructions are omitted."
            )
        return "", extra

    texts = preset_texts()
    if preset_id not in texts:
        raise ComposeEvalTextError("Select a valid system-instruction preset.")
    body = texts[preset_id]
    instructions = body if not extra else f"{body}\n\n{extra}"
    return instructions, ""
