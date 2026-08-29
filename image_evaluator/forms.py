from django import forms
from django.conf import settings


class PrepareEvaluationForm(forms.Form):
    image = forms.ImageField(
        label="Upload one image",
        widget=forms.ClearableFileInput(
            attrs={"accept": "image/png,image/jpeg,image/webp,image/gif"}
        ),
    )
    prompt = forms.CharField(
        label="Prompt used for every model",
        widget=forms.Textarea(attrs={"rows": 4}),
        initial=settings.DEFAULT_EVAL_PROMPT,
    )
    models = forms.MultipleChoiceField(
        label="Models to compare",
        choices=[(model, model) for model in settings.AVAILABLE_MODELS],
        widget=forms.CheckboxSelectMultiple,
        initial=list(settings.AVAILABLE_MODELS),
        help_text="Their order will be randomized and their identities hidden until you finish rating.",
    )

    def clean_models(self):
        selected = self.cleaned_data["models"]
        if len(selected) < 2:
            raise forms.ValidationError("Select at least two models to make a comparison.")
        return selected

    def clean_prompt(self):
        prompt = self.cleaned_data["prompt"].strip()
        if not prompt:
            raise forms.ValidationError("Enter a prompt.")
        return prompt


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
