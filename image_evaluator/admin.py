from django.contrib import admin

from .models import EvaluationRating, EvaluationRun


class EvaluationRatingInline(admin.TabularInline):
    model = EvaluationRating
    extra = 0
    readonly_fields = (
        "sample_index",
        "sample_label",
        "model",
        "rating",
        "notes",
        "latency_seconds",
        "input_tokens",
        "output_tokens",
        "response",
        "created_at",
    )


@admin.register(EvaluationRun)
class EvaluationRunAdmin(admin.ModelAdmin):
    list_display = ("id", "image_name", "created_at", "rated_count", "total_models")
    readonly_fields = ("id", "created_at", "model_order")
    inlines = [EvaluationRatingInline]


@admin.register(EvaluationRating)
class EvaluationRatingAdmin(admin.ModelAdmin):
    list_display = ("sample_label", "model", "rating", "run", "created_at")
    list_filter = ("model", "rating")
    search_fields = ("model", "notes", "response")
