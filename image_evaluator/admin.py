from django.contrib import admin

from .models import EvaluationRun, EvaluationTurn, LatencyBenchmark


class EvaluationTurnInline(admin.TabularInline):
    model = EvaluationTurn
    extra = 0
    readonly_fields = (
        "turn_index",
        "sample_label",
        "model",
        "status",
        "rating",
        "latency_wall_seconds",
        "latency_openai_seconds",
        "input_tokens",
        "output_tokens",
        "reasoning_tokens",
        "generated_at",
    )
    fields = readonly_fields


@admin.register(EvaluationRun)
class EvaluationRunAdmin(admin.ModelAdmin):
    list_display = ("id", "image_name", "status", "created_at", "turn_count", "rated_count", "is_benchmark_display")
    list_filter = ("status", "created_at")
    readonly_fields = ("id", "created_at", "completed_at", "model_order", "api_defaults")
    inlines = [EvaluationTurnInline]

    @admin.display(boolean=True, description="Benchmark")
    def is_benchmark_display(self, obj):
        return obj.is_benchmark


@admin.register(LatencyBenchmark)
class LatencyBenchmarkAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "run",
        "status",
        "started_at",
        "completed_at",
        "successful_turn_count",
        "failed_turn_count",
        "total_wall_latency_seconds",
        "avg_wall_latency_seconds",
    )
    list_filter = ("status", "started_at")
    readonly_fields = (
        "id",
        "run",
        "started_at",
        "completed_at",
        "turn_count_expected",
        "successful_turn_count",
        "failed_turn_count",
        "total_wall_latency_seconds",
        "avg_wall_latency_seconds",
    )


@admin.register(EvaluationTurn)
class EvaluationTurnAdmin(admin.ModelAdmin):
    list_display = (
        "sample_label",
        "model",
        "status",
        "rating",
        "latency_wall_seconds",
        "run",
        "generated_at",
    )
    list_filter = ("status", "model", "rating")
    search_fields = ("model", "notes", "response_text", "error_message")
    readonly_fields = ("generated_at", "updated_at", "api_request", "api_response", "usage_raw")
