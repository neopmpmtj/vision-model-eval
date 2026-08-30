"""Persistence helpers for evaluation turns and benchmarks."""

from __future__ import annotations

from datetime import datetime, timezone

from django.utils import timezone as django_timezone

from image_evaluator.models import (
    EvaluationRun,
    EvaluationTurn,
    LatencyBenchmark,
    RunStatus,
    TurnStatus,
)

from .openai_eval import AnalysisResult, ApiRequestConfig


def sample_label_for_index(index: int) -> str:
    return f"Sample {index + 1}"


def save_success_turn(
    *,
    run: EvaluationRun,
    turn_index: int,
    model: str,
    result: AnalysisResult,
) -> EvaluationTurn:
    turn, _ = EvaluationTurn.objects.update_or_create(
        run=run,
        turn_index=turn_index,
        defaults={
            "sample_label": sample_label_for_index(turn_index),
            "model": model,
            "status": TurnStatus.SUCCESS,
            "response_text": result.response_text,
            "error_message": "",
            "error_type": "",
            "openai_response_id": result.openai_response_id,
            "response_model": result.response_model,
            "openai_status": result.openai_status,
            "request_started_at": result.request_started_at,
            "request_finished_at": result.request_finished_at,
            "latency_wall_seconds": result.latency_wall_seconds,
            "latency_openai_seconds": result.latency_openai_seconds,
            "time_to_first_token_seconds": result.time_to_first_token_seconds,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "total_tokens": result.total_tokens,
            "reasoning_tokens": result.reasoning_tokens,
            "cached_tokens": result.cached_tokens,
            "cache_write_tokens": result.cache_write_tokens,
            "usage_raw": result.usage_raw,
            "api_request": result.api_request,
            "api_response": result.api_response,
        },
    )
    return turn


def save_error_turn(
    *,
    run: EvaluationRun,
    turn_index: int,
    model: str,
    error: Exception,
    request_started_at: datetime | None = None,
    request_finished_at: datetime | None = None,
    latency_wall_seconds: float | None = None,
    api_request: dict | None = None,
) -> EvaluationTurn:
    started = request_started_at or django_timezone.now()
    finished = request_finished_at or django_timezone.now()
    turn, _ = EvaluationTurn.objects.update_or_create(
        run=run,
        turn_index=turn_index,
        defaults={
            "sample_label": sample_label_for_index(turn_index),
            "model": model,
            "status": TurnStatus.ERROR,
            "response_text": "",
            "error_message": str(error),
            "error_type": type(error).__name__,
            "request_started_at": started,
            "request_finished_at": finished,
            "latency_wall_seconds": latency_wall_seconds,
            "api_request": api_request or {},
        },
    )
    return turn


def build_api_request_dict(
    *,
    model: str,
    instructions: str = "",
    user_prompt: str = "",
    api_config: ApiRequestConfig | None = None,
) -> dict:
    config = api_config or ApiRequestConfig.from_settings()
    return {
        "model": model,
        "instructions": instructions,
        "user_prompt": user_prompt,
        **config.to_dict(),
    }


def complete_benchmark(benchmark: LatencyBenchmark) -> None:
    benchmark.refresh_aggregates()
    benchmark.status = RunStatus.COMPLETED
    benchmark.completed_at = django_timezone.now()
    benchmark.save(
        update_fields=[
            "status",
            "completed_at",
            "successful_turn_count",
            "failed_turn_count",
            "total_wall_latency_seconds",
            "avg_wall_latency_seconds",
        ]
    )
    benchmark.run.status = RunStatus.COMPLETED
    benchmark.run.completed_at = benchmark.completed_at
    benchmark.run.save(update_fields=["status", "completed_at"])


def abandon_run(run: EvaluationRun) -> None:
    run.status = RunStatus.ABANDONED
    run.save(update_fields=["status"])
    if hasattr(run, "latency_benchmark"):
        benchmark = run.latency_benchmark
        benchmark.status = RunStatus.ABANDONED
        benchmark.save(update_fields=["status"])


def complete_blind_run(run: EvaluationRun) -> None:
    run.status = RunStatus.COMPLETED
    run.completed_at = django_timezone.now()
    run.save(update_fields=["status", "completed_at"])
