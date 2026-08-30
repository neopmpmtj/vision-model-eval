"""Read-only aggregations for the local console dashboard."""

from __future__ import annotations

from django.db.models import Avg, Count, Q, QuerySet, Sum

from image_evaluator.models import EvaluationRun, EvaluationTurn, RunStatus, TurnStatus

KIND_BLIND = "blind"
KIND_BENCHMARK = "benchmark"
VALID_KINDS = {KIND_BLIND, KIND_BENCHMARK}
VALID_STATUSES = {choice[0] for choice in RunStatus.choices}


def filter_runs(*, kind: str = "", status: str = "") -> QuerySet[EvaluationRun]:
    queryset = annotated_runs()
    if kind == KIND_BENCHMARK:
        queryset = queryset.filter(latency_benchmark__isnull=False)
    elif kind == KIND_BLIND:
        queryset = queryset.filter(latency_benchmark__isnull=True)
    if status in VALID_STATUSES:
        queryset = queryset.filter(status=status)
    return queryset


def annotated_runs() -> QuerySet[EvaluationRun]:
    return EvaluationRun.objects.select_related("latency_benchmark").annotate(
        n_turns=Count("turns"),
        n_success=Count("turns", filter=Q(turns__status=TurnStatus.SUCCESS)),
        n_error=Count("turns", filter=Q(turns__status=TurnStatus.ERROR)),
        n_rated=Count("turns", filter=Q(turns__rating__isnull=False)),
        avg_latency=Avg("turns__latency_wall_seconds"),
        sum_tokens=Sum("turns__total_tokens"),
    )


def console_overview() -> dict:
    runs = EvaluationRun.objects.all()
    turns = EvaluationTurn.objects.all()
    successful = turns.filter(status=TurnStatus.SUCCESS)
    latency = successful.aggregate(
        avg=Avg("latency_wall_seconds"),
        total=Sum("latency_wall_seconds"),
    )
    tokens = turns.aggregate(
        input=Sum("input_tokens"),
        output=Sum("output_tokens"),
        total=Sum("total_tokens"),
        reasoning=Sum("reasoning_tokens"),
    )
    return {
        "run_count": runs.count(),
        "in_progress": runs.filter(status=RunStatus.IN_PROGRESS).count(),
        "completed": runs.filter(status=RunStatus.COMPLETED).count(),
        "abandoned": runs.filter(status=RunStatus.ABANDONED).count(),
        "blind_count": runs.filter(latency_benchmark__isnull=True).count(),
        "benchmark_count": runs.filter(latency_benchmark__isnull=False).count(),
        "turn_count": turns.count(),
        "success_count": successful.count(),
        "error_count": turns.filter(status=TurnStatus.ERROR).count(),
        "rated_count": turns.filter(rating__isnull=False).count(),
        "avg_wall_latency": latency["avg"],
        "total_wall_latency": latency["total"],
        "total_input_tokens": tokens["input"] or 0,
        "total_output_tokens": tokens["output"] or 0,
        "total_tokens": tokens["total"] or 0,
        "total_reasoning_tokens": tokens["reasoning"] or 0,
    }


def model_summaries() -> list[dict]:
    return list(
        EvaluationTurn.objects.values("model")
        .annotate(
            turns=Count("id"),
            successes=Count("id", filter=Q(status=TurnStatus.SUCCESS)),
            errors=Count("id", filter=Q(status=TurnStatus.ERROR)),
            avg_latency=Avg("latency_wall_seconds"),
            avg_rating=Avg("rating"),
            total_tokens=Sum("total_tokens"),
        )
        .order_by("model")
    )


def recent_runs(limit: int = 5) -> QuerySet[EvaluationRun]:
    return annotated_runs()[:limit]


def session_url_name(run: EvaluationRun) -> str:
    if run.is_complete:
        return "image_evaluator:results"
    if run.is_benchmark:
        return "image_evaluator:benchmark"
    return "image_evaluator:evaluate"
