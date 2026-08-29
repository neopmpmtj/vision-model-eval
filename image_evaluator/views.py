import csv
import io

from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from .forms import PrepareEvaluationForm, RatingForm
from .models import EvaluationRating, EvaluationRun
from .services import analyze_image, shuffle_models, validate_api_key
from .services.api_key import ApiKeyStatus

SESSION_PENDING_KEY = "pending_analysis"
SESSION_ERROR_KEY = "request_error"
SESSION_API_KEY_STATUS = "openai_api_key_status"


def _clear_pending(request) -> None:
    request.session.pop(SESSION_PENDING_KEY, None)
    request.session.pop(SESSION_ERROR_KEY, None)


def _status_from_session(data: dict) -> ApiKeyStatus:
    return ApiKeyStatus(
        ok=data["ok"],
        message=data["message"],
        missing_models=data.get("missing_models", []),
        checked_models=data.get("checked_models", []),
    )


def _check_api_key(request) -> HttpResponse | None:
    if not settings.OPENAI_API_KEY:
        return render(
            request,
            "image_evaluator/missing_api_key.html",
            status=503,
        )

    if request.GET.get("recheck") == "1":
        request.session.pop(SESSION_API_KEY_STATUS, None)

    cached = request.session.get(SESSION_API_KEY_STATUS)
    if cached and cached.get("key") == settings.OPENAI_API_KEY:
        status = _status_from_session(cached)
    else:
        status = validate_api_key()
        request.session[SESSION_API_KEY_STATUS] = {
            "key": settings.OPENAI_API_KEY,
            "ok": status.ok,
            "message": status.message,
            "missing_models": status.missing_models,
            "checked_models": status.checked_models,
        }

    if not status.ok:
        return render(
            request,
            "image_evaluator/invalid_api_key.html",
            {"status": status},
            status=503,
        )
    return None


class PrepareView(View):
    template_name = "image_evaluator/prepare.html"

    def get(self, request):
        blocked = _check_api_key(request)
        if blocked:
            return blocked
        form = PrepareEvaluationForm()
        return render(request, self.template_name, {"form": form})

    def post(self, request):
        blocked = _check_api_key(request)
        if blocked:
            return blocked

        form = PrepareEvaluationForm(request.POST, request.FILES)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})

        uploaded = form.cleaned_data["image"]
        model_order = shuffle_models(form.cleaned_data["models"])
        run = EvaluationRun.objects.create(
            image=uploaded,
            image_name=uploaded.name,
            image_content_type=getattr(uploaded, "content_type", None) or "image/jpeg",
            prompt=form.cleaned_data["prompt"],
            model_order=model_order,
        )
        _clear_pending(request)
        return redirect("image_evaluator:evaluate", run_id=run.id)


class EvaluateView(View):
    template_name = "image_evaluator/evaluate.html"

    def get(self, request, run_id):
        blocked = _check_api_key(request)
        if blocked:
            return blocked

        run = get_object_or_404(EvaluationRun, pk=run_id)
        if run.is_complete:
            return redirect("image_evaluator:results", run_id=run.id)

        current_index = run.current_index
        pending = request.session.get(SESSION_PENDING_KEY)
        pending_for_sample = (
            pending
            if pending and pending.get("run_id") == str(run.id) and pending.get("sample_index") == current_index
            else None
        )

        context = {
            "run": run,
            "sample_name": f"Sample {current_index + 1}",
            "current_index": current_index,
            "total_models": run.total_models,
            "progress_pct": int((current_index / run.total_models) * 100) if run.total_models else 0,
            "pending": pending_for_sample,
            "rating_form": RatingForm() if pending_for_sample else None,
            "request_error": request.session.get(SESSION_ERROR_KEY),
        }
        return render(request, self.template_name, context)

    def post(self, request, run_id):
        blocked = _check_api_key(request)
        if blocked:
            return blocked

        run = get_object_or_404(EvaluationRun, pk=run_id)
        if run.is_complete:
            return redirect("image_evaluator:results", run_id=run.id)

        action = request.POST.get("action")
        current_index = run.current_index

        if action == "generate":
            model = run.model_order[current_index]
            try:
                result = analyze_image(
                    model=model,
                    prompt=run.prompt,
                    image_path=run.image.path,
                    image_content_type=run.image_content_type,
                )
                request.session[SESSION_PENDING_KEY] = {
                    "run_id": str(run.id),
                    "sample_index": current_index,
                    "model": model,
                    "response": result.response_text,
                    "latency_seconds": result.latency_seconds,
                    "input_tokens": result.input_tokens,
                    "output_tokens": result.output_tokens,
                }
                request.session.pop(SESSION_ERROR_KEY, None)
            except Exception as exc:
                request.session.pop(SESSION_PENDING_KEY, None)
                request.session[SESSION_ERROR_KEY] = str(exc)
                messages.error(
                    request,
                    "The request failed. Check your API access, credit, connection, and model availability.",
                )
            return redirect("image_evaluator:evaluate", run_id=run.id)

        if action == "rate":
            pending = request.session.get(SESSION_PENDING_KEY)
            if not (
                pending
                and pending.get("run_id") == str(run.id)
                and pending.get("sample_index") == current_index
            ):
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
                        "pending": pending,
                        "rating_form": form,
                        "request_error": None,
                    },
                )

            EvaluationRating.objects.create(
                run=run,
                sample_index=current_index,
                sample_label=f"Sample {current_index + 1}",
                model=pending["model"],
                rating=form.cleaned_data["rating"],
                notes=form.cleaned_data["notes"].strip(),
                latency_seconds=pending["latency_seconds"],
                input_tokens=pending["input_tokens"],
                output_tokens=pending["output_tokens"],
                response=pending["response"],
            )
            _clear_pending(request)
            run.refresh_from_db()
            if run.is_complete:
                return redirect("image_evaluator:results", run_id=run.id)
            return redirect("image_evaluator:evaluate", run_id=run.id)

        return redirect("image_evaluator:evaluate", run_id=run.id)


class ResultsView(View):
    template_name = "image_evaluator/results.html"

    def get(self, request, run_id):
        run = get_object_or_404(EvaluationRun, pk=run_id)
        if not run.is_complete:
            return redirect("image_evaluator:evaluate", run_id=run.id)
        ratings = run.ratings.select_related().all()
        return render(
            request,
            self.template_name,
            {"run": run, "ratings": ratings},
        )


class DownloadCsvView(View):
    def get(self, request, run_id):
        run = get_object_or_404(EvaluationRun, pk=run_id)
        if not run.is_complete:
            return redirect("image_evaluator:evaluate", run_id=run.id)

        buffer = io.StringIO()
        fields = [
            "timestamp_utc",
            "run_id",
            "sample",
            "model",
            "image_name",
            "prompt",
            "rating",
            "notes",
            "latency_seconds",
            "input_tokens",
            "output_tokens",
            "response",
        ]
        writer = csv.DictWriter(buffer, fieldnames=fields)
        writer.writeheader()
        for rating in run.ratings.all():
            writer.writerow(
                {
                    "timestamp_utc": rating.created_at.isoformat(),
                    "run_id": str(run.id),
                    "sample": rating.sample_label,
                    "model": rating.model,
                    "image_name": run.image_name,
                    "prompt": run.prompt,
                    "rating": rating.rating,
                    "notes": rating.notes,
                    "latency_seconds": rating.latency_seconds,
                    "input_tokens": rating.input_tokens,
                    "output_tokens": rating.output_tokens,
                    "response": rating.response,
                }
            )

        response = HttpResponse(buffer.getvalue(), content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="image-comparison-{run.id}.csv"'
        )
        return response


class ResetView(View):
    def post(self, request, run_id=None):
        _clear_pending(request)
        return redirect("image_evaluator:prepare")
