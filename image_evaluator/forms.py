from django import forms
from django.conf import settings
from django.db import models

from image_evaluator.model_catalog import (
    all_enabled_model_choices,
    default_lab_id,
    enabled_labs,
    models_for_lab,
)
from image_evaluator.prompt_presets import (
    ComposeEvalTextError,
    compose_eval_text,
    default_preset_id,
    preset_choices,
)
from image_evaluator.services.openai_eval import ApiRequestConfig

# openai.types.shared.reasoning_effort.ReasoningEffort
REASONING_EFFORT_CHOICES = [
    ("none", "none"),
    ("minimal", "minimal"),
    ("low", "low"),
    ("medium", "medium"),
    ("high", "high"),
    ("xhigh", "xhigh"),
    ("max", "max"),
]

# openai.types.shared_params.reasoning.Reasoning mode
REASONING_MODE_CHOICES = [
    ("standard", "standard"),
    ("pro", "pro"),
]

# openai.types.responses.response_input_image_param.ResponseInputImageParam.detail
IMAGE_DETAIL_CHOICES = [
    ("auto", "auto"),
    ("low", "low"),
    ("high", "high"),
    ("original", "original"),
]


class RunType(models.TextChoices):
    BLIND_COMPARISON = "blind_comparison", "Blind comparison (rate responses)"
    LATENCY_BENCHMARK = "latency_benchmark", "Latency benchmark (no ratings)"


class PrepareEvaluationForm(forms.Form):
    run_type = forms.ChoiceField(
        label="Session type",
        choices=RunType.choices,
        initial=RunType.BLIND_COMPARISON,
        widget=forms.RadioSelect,
    )
    lab = forms.ChoiceField(
        label="Model lab",
        choices=[],
        initial=default_lab_id,
    )
    image = forms.ImageField(
        label="Upload one image",
        widget=forms.ClearableFileInput(
            attrs={"accept": "image/png,image/jpeg,image/webp,image/gif"}
        ),
    )
    description = forms.CharField(
        label="Session description",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Optional. What this session is for — used to find it later.",
    )
    omit_instructions = forms.BooleanField(
        label="Omit system instructions",
        required=False,
        initial=False,
        help_text="Send only additional text as the user prompt (for short yes/no questions).",
    )
    prompt_preset = forms.ChoiceField(
        label="System instructions",
        choices=[],
        initial=default_preset_id,
        help_text="Sent as Responses API instructions (system/developer message).",
    )
    additional = forms.CharField(
        label="Additional instructions",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Appended to the preset when system instructions are on. Required when they are omitted.",
    )
    models = forms.MultipleChoiceField(
        label="Models to compare",
        choices=[],
        widget=forms.CheckboxSelectMultiple,
        help_text="Their order will be randomized in blind mode. Benchmark mode runs them sequentially.",
    )
    reasoning_effort = forms.ChoiceField(
        label="Reasoning effort",
        choices=REASONING_EFFORT_CHOICES,
        initial=settings.OPENAI_DEFAULT_REASONING_EFFORT,
    )
    reasoning_mode = forms.ChoiceField(
        label="Reasoning mode",
        choices=REASONING_MODE_CHOICES,
        initial=settings.OPENAI_DEFAULT_REASONING_MODE,
        help_text="GPT-5 and o-series models only.",
    )
    max_output_tokens = forms.IntegerField(
        label="Max output tokens",
        min_value=1,
        max_value=128000,
        initial=settings.OPENAI_DEFAULT_MAX_OUTPUT_TOKENS,
    )
    image_detail = forms.ChoiceField(
        label="Image detail",
        choices=IMAGE_DETAIL_CHOICES,
        initial=settings.OPENAI_DEFAULT_IMAGE_DETAIL,
        help_text="Responses API input_image detail parameter.",
    )
    store = forms.BooleanField(
        label="Store responses on OpenAI",
        required=False,
        initial=settings.OPENAI_DEFAULT_STORE,
        help_text="When unchecked, the API is called with store=false.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["lab"].choices = enabled_labs()
        self.fields["prompt_preset"].choices = preset_choices()
        lab_id = self._selected_lab_id()
        lab_models = models_for_lab(lab_id)
        self.fields["models"].choices = all_enabled_model_choices()
        if not self.is_bound:
            self.fields["models"].initial = lab_models

    def _selected_lab_id(self) -> str:
        if self.is_bound:
            return self.data.get("lab") or default_lab_id()
        if self.initial.get("lab"):
            return self.initial["lab"]
        return default_lab_id()

    def clean_lab(self):
        lab_id = self.cleaned_data["lab"]
        if lab_id not in dict(enabled_labs()):
            raise forms.ValidationError("Select an enabled model lab.")
        return lab_id

    def clean_models(self):
        selected = self.cleaned_data["models"]
        lab_id = self.cleaned_data.get("lab") or self._selected_lab_id()
        allowed = set(models_for_lab(lab_id))
        invalid = [model for model in selected if model not in allowed]
        if invalid:
            raise forms.ValidationError("One or more models are not available for the selected lab.")
        if len(selected) < 2:
            raise forms.ValidationError("Select at least two models to make a comparison.")
        return selected

    def clean_description(self):
        return self.cleaned_data["description"].strip()

    def clean_prompt_preset(self):
        preset_id = self.cleaned_data["prompt_preset"]
        valid_ids = {choice[0] for choice in preset_choices()}
        if preset_id not in valid_ids:
            raise forms.ValidationError("Select a valid system-instruction preset.")
        return preset_id

    def clean_additional(self):
        return self.cleaned_data["additional"].strip()

    def clean(self):
        cleaned = super().clean()
        omit = cleaned.get("omit_instructions")
        preset_id = cleaned.get("prompt_preset") or default_preset_id()
        additional = cleaned.get("additional", "")
        try:
            instructions, user_prompt = compose_eval_text(
                omit_instructions=bool(omit),
                preset_id=preset_id,
                additional=additional,
            )
        except ComposeEvalTextError as exc:
            raise forms.ValidationError(str(exc)) from exc
        cleaned["instructions"] = instructions
        cleaned["user_prompt"] = user_prompt
        return cleaned

    def api_defaults_dict(self) -> dict:
        config = ApiRequestConfig(
            reasoning_effort=self.cleaned_data["reasoning_effort"],
            reasoning_mode=self.cleaned_data["reasoning_mode"],
            max_output_tokens=self.cleaned_data["max_output_tokens"],
            store=self.cleaned_data["store"],
            image_detail=self.cleaned_data["image_detail"],
        ).to_dict()
        config["lab"] = self.cleaned_data["lab"]
        config["omit_instructions"] = bool(self.cleaned_data["omit_instructions"])
        config["prompt_preset"] = self.cleaned_data["prompt_preset"]
        return config


class RatingForm(forms.Form):
    rating = forms.IntegerField(
        label="Your rating",
        min_value=1,
        max_value=5,
        initial=3,
        widget=forms.NumberInput(attrs={"type": "range", "min": 1, "max": 5, "step": 1}),
    )
    notes = forms.CharField(
        label="Optional notes",
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "What was correct, missed, vague, or especially useful?",
            }
        ),
    )
