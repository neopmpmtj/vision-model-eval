"""Model lab catalog helpers."""

from __future__ import annotations

from django.conf import settings


def enabled_labs() -> list[tuple[str, str]]:
    return [
        (lab_id, lab["label"])
        for lab_id, lab in settings.MODEL_LABS.items()
        if lab.get("enabled")
    ]


def disabled_labs() -> list[tuple[str, str]]:
    return [
        (lab_id, lab["label"])
        for lab_id, lab in settings.MODEL_LABS.items()
        if not lab.get("enabled")
    ]


def default_lab_id() -> str:
    for lab_id, lab in settings.MODEL_LABS.items():
        if lab.get("enabled"):
            return lab_id
    return next(iter(settings.MODEL_LABS))


def models_for_lab(lab_id: str) -> list[str]:
    lab = settings.MODEL_LABS.get(lab_id, {})
    return list(lab.get("models", []))


def lab_model_choices(lab_id: str) -> list[tuple[str, str]]:
    return [(model, model) for model in models_for_lab(lab_id)]


def all_enabled_model_choices() -> list[tuple[str, str]]:
    choices: list[tuple[str, str]] = []
    for lab_id, lab in settings.MODEL_LABS.items():
        if lab.get("enabled"):
            choices.extend(lab_model_choices(lab_id))
    return choices


def model_to_lab_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for lab_id, lab in settings.MODEL_LABS.items():
        if lab.get("enabled"):
            for model in lab.get("models", []):
                mapping[model] = lab_id
    return mapping
