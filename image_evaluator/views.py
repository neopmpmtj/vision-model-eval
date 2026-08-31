import csv
import io
import time
from datetime import datetime, timezone

from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone as django_timezone
from django.views import View

from .forms import PrepareEvaluationForm, RatingForm, RunType
from .image_utils import extract_image_metadata
from .models import EvaluationRun, EvaluationTurn, LatencyBenchmark, RunStatus, TurnStatus
from .services import (
    abandon_run,
    analyze_image,
    api_key_for_lab,
    build_api_request_dict,
    complete_benchmark,
    complete_blind_run,
    lab_key_alerts_for_prepare,
    lab_key_context,
    save_error_turn,
    save_success_turn,
    session_key_for_lab,
    shuffle_models,
    validate_lab_api_key,
)
from .services.api_key import ApiKeyStatus
from .services.console import console_overview, filter_runs, model_summaries, session_url_name
from .model_catalog import disabled_labs, model_to_lab_map

SESSION_PENDING_TURN_KEY = "pending_turn_id"
SESSION_ERROR_KEY = "request_error"


def _clear_pending(request) -> None:
    request.session.pop(SESSION_PENDING_TURN_KEY, None)
    request.session.pop(SESSION_ERROR_KEY, None)


def _status_from_session(data: dict) -> ApiKeyStatus:
    return ApiKeyStatus(
        ok=data["ok"],
        message=data["message"],
        missing_models=data.get("missing_models", []),
        checked_models=data.get("checked_models", []),
    )


def _lab_for_run(run: EvaluationRun) -> str:
    return str(run.api_defaults.get("lab") or "openai")


def _check_api_key(request, lab_id: str) -> HttpResponse | None:
    key = api_key_for_lab(lab_id)
    if not key:
        return render(
            request,
            "image_evaluator/missing_api_key.html",
            {"lab": lab_key_context(lab_id)},
            status=503,
        )

    session_key = session_key_for_lab(lab_id)
    if request.GET.get("recheck") == "1":
        request.session.pop(session_key, None)

    cached = request.session.get(session_key)
    if cached and cached.get("key") == key:
        status = _status_from_session(cached)
    else:
        status = validate_lab_api_key(lab_id)
        request.session[session_key] = {
            "key": key,
            "ok": status.ok,
            "message": status.message,
            "missing_models": status.missing_models,
            "checked_models": status.checked_models,
        }

    if not status.ok:
        return render(
            request,
            "image_evaluator/invalid_api_key.html",
            {"status": status, "lab": lab_key_context(lab_id)},
            status=503,
        )
    return None


def _create_run(
    *,
    uploaded,
    instructions: str,
    user_prompt: str,
    description: str,
    model_order: list[str],
    api_defaults: dict,
) -> EvaluationRun:
    size_bytes, width, height = extract_image_metadata(uploaded)
    return EvaluationRun.objects.create(
        image=uploaded,
        image_name=uploaded.name,
        image_content_type=getattr(uploaded, "content_type", None) or "image/jpeg",
        image_size_bytes=size_bytes,
        image_width=width,
        image_height=height,
        instructions=instructions,
        user_prompt=user_prompt,
        description=description,
        model_order=model_order,
        api_defaults=api_defaults,
        status=RunStatus.IN_PROGRESS,
    )


def _turn_csv_fields() -> list[str]:
    return [
        "timestamp_utc",
        "run_id",
        "benchmark_id",
        "turn_index",
        "sample",
        "model",
        "response_model",
        "status",
        "image_name",
        "instructions",
        "user_prompt",
        "session_description",
        "rating",
        "notes",
        "rated_at",
        "request_started_at",
        "request_finished_at",
        "latency_wall_seconds",
        "latency_openai_seconds",
        "time_to_first_token_seconds",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "reasoning_tokens",
        "cached_tokens",
        "cache_write_tokens",
        "openai_response_id",
        "openai_status",
        "error_type",
        "error_message",
        "api_request",
        "api_response",
        "usage_raw",
        "response",
    ]


def _turn_csv_row(*, run: EvaluationRun, turn: EvaluationTurn) -> dict:
    benchmark_id = ""
    if run.is_benchmark:
        benchmark_id = str(run.latency_benchmark.id)
    return {
        "timestamp_utc": turn.generated_at.isoformat(),
        "run_id": str(run.id),
        "benchmark_id": benchmark_id,
        "turn_index": turn.turn_index,
        "sample": turn.sample_label,
        "model": turn.model,
        "response_model": turn.response_model,
        "status": turn.status,
        "image_name": run.image_name,
        "instructions": run.instructions,
        "user_prompt": run.user_prompt,
        "session_description": run.description,
        "rating": turn.rating if turn.rating is not None else "",
        "notes": turn.notes,
        "rated_at": turn.rated_at.isoformat() if turn.rated_at else "",
        "request_started_at": turn.request_started_at.isoformat() if turn.request_started_at else "",
        "request_finished_at": turn.request_finished_at.isoformat() if turn.request_finished_at else "",
        "latency_wall_seconds": turn.latency_wall_seconds,
        "latency_openai_seconds": turn.latency_openai_seconds,
        "time_to_first_token_seconds": turn.time_to_first_token_seconds,
        "input_tokens": turn.input_tokens,
        "output_tokens": turn.output_tokens,
        "total_tokens": turn.total_tokens,
        "reasoning_tokens": turn.reasoning_tokens,
        "cached_tokens": turn.cached_tokens,
        "cache_write_tokens": turn.cache_write_tokens,
        "openai_response_id": turn.openai_response_id,
        "openai_status": turn.openai_status,
        "error_type": turn.error_type,
        "error_message": turn.error_message,
        "api_request": turn.api_request,
        "api_response": turn.api_response,
        "usage_raw": turn.usage_raw,
        "response": turn.response_text,
    }


class ConsoleView(View):
    template_name = "image_evaluator/console.html"

    def get(self, request):
        kind = request.GET.get("kind", "")
        status = request.GET.get("status", "")
        return render(
            request,
            self.template_name,
            {
                "overview": console_overview(),
                "model_summaries": model_summaries(),
                "runs": filter_runs(kind=kind, status=status),
                "kind_filter": kind,
                "status_filter": status,
            },
        )


class InspectRunView(View):
    template_name = "image_evaluator/inspect_run.html"

    def get(self, request, run_id):
        run = get_object_or_404(EvaluationRun.objects.select_related("latency_benchmark"), pk=run_id)
        turns = run.turns.all()
        benchmark = getattr(run, "latency_benchmark", None)
        return render(
            request,
            self.template_name,
            {
                "run": run,
                "turns": turns,
                "benchmark": benchmark,
                "session_url": reverse(session_url_name(run), kwargs={"run_id": run.id}),
            },
        )


class InspectTurnView(View):
    template_name = "image_evaluator/inspect_turn.html"

    def get(self, request, run_id, turn_index):
        run = get_object_or_404(EvaluationRun, pk=run_id)
        turn = get_object_or_404(run.turns, turn_index=turn_index)
        return render(
            request,
            self.template_name,
            {"run": run, "turn": turn},
        )


class PrepareView(View):
    template_name = "image_evaluator/prepare.html"

    def _prepare_context(self, form: PrepareEvaluationForm, *, request=None) -> dict:
        return {
            "form": form,
            "disabled_labs": disabled_labs(),
            "model_to_lab": model_to_lab_map(),
            "lab_key_alerts": lab_key_alerts_for_prepare(request) if request else {},
        }

    def get(self, request):
        form = PrepareEvaluationForm()
        return render(
            request,
            self.template_name,
            self._prepare_context(form, request=request),
        )

    def post(self, request):
        form = PrepareEvaluationForm(request.POST, request.FILES)
        if not form.is_valid():
            return render(
                request,
                self.template_name,
                self._prepare_context(form, request=request),
            )

        lab_id = form.cleaned_data["lab"]
        blocked = _check_api_key(request, lab_id)
        if blocked:
            return blocked

        uploaded = form.cleaned_data["image"]
        model_order = (
            shuffle_models(form.cleaned_data["models"])
            if form.cleaned_data["run_type"] == RunType.BLIND_COMPARISON
            else list(form.cleaned_data["models"])
        )
        run = _create_run(
            uploaded=uploaded,
            instructions=form.cleaned_data["instructions"],
            user_prompt=form.cleaned_data["user_prompt"],
            description=form.cleaned_data["description"],
            model_order=model_order,
            api_defaults=form.api_defaults_dict(),
        )
        _clear_pending(request)

        if form.cleaned_data["run_type"] == RunType.LATENCY_BENCHMARK:
            LatencyBenchmark.objects.create(
                run=run,
                status=RunStatus.IN_PROGRESS,
                turn_count_expected=len(model_order),
            )
            return redirect("image_evaluator:benchmark", run_id=run.id)

        return redirect("image_evaluator:evaluate", run_id=run.id)


class EvaluateView(View):
    template_name = "image_evaluator/evaluate.html"

    def get(self, request, run_id):
        run = get_object_or_404(EvaluationRun, pk=run_id)
        blocked = _check_api_key(request, _lab_for_run(run))
        if blocked:
            return blocked
        if run.is_benchmark:
            return redirect("image_evaluator:benchmark", run_id=run.id)
        if run.is_complete:
            return redirect("image_evaluator:results", run_id=run.id)

        current_index = run.current_index
        pending_turn = None
        pending_turn_id = request.session.get(SESSION_PENDING_TURN_KEY)
        if pending_turn_id:
            pending_turn = run.turns.filter(pk=pending_turn_id, turn_index=current_index).first()
        if pending_turn is None:
            pending_turn = run.turns.filter(
                turn_index=current_index,
                status=TurnStatus.SUCCESS,
                rating__isnull=True,
            ).first()

        context = {
            "run": run,
            "sample_name": f"Sample {current_index + 1}",
            "current_index": current_index,
            "total_models": run.total_models,
            "progress_pct": int((current_index / run.total_models) * 100) if run.total_models else 0,
            "pending_turn": pending_turn,
            "rating_form": RatingForm() if pending_turn else None,
            "request_error": request.session.get(SESSION_ERROR_KEY),
        }
        return render(request, self.template_name, context)

    def post(self, request, run_id):
        run = get_object_or_404(EvaluationRun, pk=run_id)
        blocked = _check_api_key(request, _lab_for_run(run))
        if blocked:
            return blocked
        if run.is_benchmark:
            return redirect("image_evaluator:benchmark", run_id=run.id)
        if run.is_complete:
            return redirect("image_evaluator:results", run_id=run.id)

        action = request.POST.get("action")
        current_index = run.current_index

        if action == "generate":
            model = run.model_order[current_index]
            lab_id = _lab_for_run(run)
            started_perf = time.perf_counter()
            request_started_at = datetime.now(timezone.utc)
            try:
                result = analyze_image(
                    lab=lab_id,
                    model=model,
                    instructions=run.instructions,
                    user_prompt=run.user_prompt,
                    image_path=run.image.path,
                    image_content_type=run.image_content_type,
                    api_defaults=run.api_defaults,
                )
                turn = save_success_turn(
                    run=run,
                    turn_index=current_index,
                    model=model,
                    result=result,
                )
                request.session[SESSION_PENDING_TURN_KEY] = turn.pk
                request.session.pop(SESSION_ERROR_KEY, None)
            except Exception as exc:
                save_error_turn(
                    run=run,
                    turn_index=current_index,
                    model=model,
                    error=exc,
                    request_started_at=request_started_at,
                    request_finished_at=datetime.now(timezone.utc),
                    latency_wall_seconds=round(time.perf_counter() - started_perf, 3),
                    api_request=build_api_request_dict(
                        lab=lab_id,
                        model=model,
                        instructions=run.instructions,
                        user_prompt=run.user_prompt,
                        api_defaults=run.api_defaults,
                    ),
                )
                request.session.pop(SESSION_PENDING_TURN_KEY, None)
                request.session[SESSION_ERROR_KEY] = str(exc)
                messages.error(
                    request,
                    "The request failed. Check your API access, credit, connection, and model availability.",
                )
            return redirect("image_evaluator:evaluate", run_id=run.id)

        if action == "rate":
            pending_turn_id = request.session.get(SESSION_PENDING_TURN_KEY)
            turn = run.turns.filter(pk=pending_turn_id, turn_index=current_index).first()
            if turn is None or turn.status != TurnStatus.SUCCESS:
                messages.error(request, "Generate a response before rating.")
                return redirect("image_evaluator:evaluate", run_id=run.id)

            form = RatingForm(request.POST)
            if not form.is_valid():
                return render(
                    request,
                    self.template_name,
                    {
                        "run": run,
                        "sample_name": f"Sample {current_index + 1}",
                        "current_index": current_index,
                        "total_models": run.total_models,
                        "progress_pct": int((current_index / run.total_models) * 100),
                        "pending_turn": turn,
                        "rating_form": form,
                        "request_error": None,
                    },
                )

            turn.rating = form.cleaned_data["rating"]
            turn.notes = form.cleaned_data["notes"].strip()
            turn.rated_at = django_timezone.now()
            turn.save(update_fields=["rating", "notes", "rated_at", "updated_at"])
            _clear_pending(request)
            run.refresh_from_db()
            if run.is_complete:
                complete_blind_run(run)
                return redirect("image_evaluator:results", run_id=run.id)
            return redirect("image_evaluator:evaluate", run_id=run.id)

        return redirect("image_evaluator:evaluate", run_id=run.id)


def _pending_benchmark_indices(run: EvaluationRun) -> list[int]:
    return [
        index
        for index in range(len(run.model_order))
        if not run.turns.filter(turn_index=index).exists()
    ]


def _run_benchmark_turn(
    *,
    run: EvaluationRun,
    turn_index: int,
    model: str,
) -> None:
    lab_id = _lab_for_run(run)
    started_perf = time.perf_counter()
    request_started_at = datetime.now(timezone.utc)
    try:
        result = analyze_image(
            lab=lab_id,
            model=model,
            instructions=run.instructions,
            user_prompt=run.user_prompt,
            image_path=run.image.path,
            image_content_type=run.image_content_type,
            api_defaults=run.api_defaults,
        )
        save_success_turn(
            run=run,
            turn_index=turn_index,
            model=model,
            result=result,
        )
    except Exception as exc:
        save_error_turn(
            run=run,
            turn_index=turn_index,
            model=model,
            error=exc,
            request_started_at=request_started_at,
            request_finished_at=datetime.now(timezone.utc),
            latency_wall_seconds=round(time.perf_counter() - started_perf, 3),
            api_request=build_api_request_dict(
                lab=lab_id,
                model=model,
                instructions=run.instructions,
                user_prompt=run.user_prompt,
                api_defaults=run.api_defaults,
            ),
        )


class BenchmarkView(View):
    template_name = "image_evaluator/benchmark.html"

    def get(self, request, run_id):
        run = get_object_or_404(EvaluationRun, pk=run_id)
        blocked = _check_api_key(request, _lab_for_run(run))
        if blocked:
            return blocked
        benchmark = get_object_or_404(LatencyBenchmark, run=run)
        if benchmark.status == RunStatus.COMPLETED:
            return redirect("image_evaluator:results", run_id=run.id)

        pending = _pending_benchmark_indices(run)

        if not pending:
            complete_benchmark(benchmark)
            return redirect("image_evaluator:results", run_id=run.id)

        should_run = run.turn_count == 0 or request.GET.get("continue") == "1"
        if should_run:
            turn_index = pending[0]
            model = run.model_order[turn_index]
            _run_benchmark_turn(
                run=run,
                turn_index=turn_index,
                model=model,
            )
            run.refresh_from_db()
            pending = _pending_benchmark_indices(run)
            if not pending:
                complete_benchmark(benchmark)
                return redirect("image_evaluator:results", run_id=run.id)

        pending = _pending_benchmark_indices(run)
        next_model = run.model_order[pending[0]] if pending else ""
        completed_count = run.turn_count
        total_models = run.total_models
        return render(
            request,
            self.template_name,
            {
                "run": run,
                "benchmark": benchmark,
                "turns": run.turns.all(),
                "next_model": next_model,
                "completed_count": completed_count,
                "total_models": total_models,
                "progress_pct": int((completed_count / total_models) * 100) if total_models else 0,
            },
        )


class ResultsView(View):
    template_name = "image_evaluator/results.html"

    def get(self, request, run_id):
        run = get_object_or_404(EvaluationRun, pk=run_id)
        if not run.is_complete:
            if run.is_benchmark:
                return redirect("image_evaluator:benchmark", run_id=run.id)
            return redirect("image_evaluator:evaluate", run_id=run.id)
        turns = run.turns.all()
        benchmark = getattr(run, "latency_benchmark", None)
        return render(
            request,
            self.template_name,
            {"run": run, "turns": turns, "benchmark": benchmark},
        )


class DownloadCsvView(View):
    def get(self, request, run_id):
        run = get_object_or_404(EvaluationRun, pk=run_id)
        turns = run.turns.all()
        if not turns.exists():
            return redirect("image_evaluator:inspect", run_id=run.id)

        buffer = io.StringIO()
        fields = _turn_csv_fields()
        writer = csv.DictWriter(buffer, fieldnames=fields)
        writer.writeheader()
        for turn in run.turns.all():
            row = _turn_csv_row(run=run, turn=turn)
            row["api_request"] = str(row["api_request"])
            row["api_response"] = str(row["api_response"])
            row["usage_raw"] = str(row["usage_raw"])
            writer.writerow(row)

        response = HttpResponse(buffer.getvalue(), content_type="text/csv")
        filename = f"benchmark-{run.id}.csv" if run.is_benchmark else f"comparison-{run.id}.csv"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class ResetView(View):
    def post(self, request, run_id=None):
        if run_id:
            run = EvaluationRun.objects.filter(pk=run_id).first()
            if run and run.status == RunStatus.IN_PROGRESS and run.turn_count > 0:
                abandon_run(run)
        _clear_pending(request)
        return redirect("image_evaluator:prepare")
