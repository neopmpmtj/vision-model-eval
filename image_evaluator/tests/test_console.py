from datetime import datetime, timezone
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from PIL import Image

from image_evaluator.models import (
    EvaluationRun,
    EvaluationTurn,
    LatencyBenchmark,
    RunStatus,
    TurnStatus,
)
from image_evaluator.services.openai_eval import ApiRequestConfig


def make_test_image() -> SimpleUploadedFile:
    image = Image.new("RGB", (8, 8), color="red")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return SimpleUploadedFile("test.png", buffer.read(), content_type="image/png")


def make_run(*, benchmark: bool = False, image_name: str = "test.png") -> EvaluationRun:
    run = EvaluationRun.objects.create(
        image=make_test_image(),
        image_name=image_name,
        image_content_type="image/png",
        image_size_bytes=100,
        image_width=8,
        image_height=8,
        user_prompt="describe this image",
        model_order=["gpt-a", "gpt-b"],
        api_defaults=ApiRequestConfig.from_settings().to_dict(),
        status=RunStatus.IN_PROGRESS,
    )
    if benchmark:
        LatencyBenchmark.objects.create(run=run, turn_count_expected=2)
    return run


class ConsoleViewTests(TestCase):
    def test_console_loads_without_api_key(self):
        response = Client().get(reverse("image_evaluator:console"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Console")

    def test_console_lists_runs(self):
        blind = make_run()
        benchmark = make_run(benchmark=True)
        response = Client().get(reverse("image_evaluator:console"))
        self.assertContains(response, blind.image_name)
        self.assertContains(response, benchmark.image_name)

    def test_console_kind_filter(self):
        make_run(image_name="blind-only.png")
        benchmark = make_run(benchmark=True, image_name="bench-only.png")
        response = Client().get(reverse("image_evaluator:console"), {"kind": "benchmark"})
        self.assertNotContains(response, "blind-only.png")
        self.assertContains(response, "bench-only.png")

    def test_console_status_filter(self):
        run = make_run()
        run.status = RunStatus.ABANDONED
        run.save()
        response = Client().get(reverse("image_evaluator:console"), {"status": "abandoned"})
        self.assertContains(response, run.image_name)


class InspectViewTests(TestCase):
    def test_inspect_in_progress_run(self):
        run = make_run()
        EvaluationTurn.objects.create(
            run=run,
            turn_index=0,
            sample_label="Sample 1",
            model="gpt-a",
            status=TurnStatus.SUCCESS,
            response_text="hello",
            api_request={"model": "gpt-a"},
            api_response={"id": "resp_1"},
            usage_raw={"input_tokens": 5},
        )
        response = Client().get(reverse("image_evaluator:inspect", kwargs={"run_id": run.id}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "gpt-a")
        self.assertContains(response, "Continue")

    def test_inspect_turn_shows_json(self):
        run = make_run()
        EvaluationTurn.objects.create(
            run=run,
            turn_index=0,
            sample_label="Sample 1",
            model="gpt-a",
            status=TurnStatus.SUCCESS,
            response_text="hello",
            api_request={"model": "gpt-a", "reasoning": {"effort": "low"}},
            api_response={"id": "resp_1", "status": "completed"},
            usage_raw={"input_tokens": 5},
        )
        response = Client().get(
            reverse("image_evaluator:inspect_turn", kwargs={"run_id": run.id, "turn_index": 0})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "API request")
        self.assertContains(response, "resp_1")
        self.assertContains(response, "hello")

    def test_csv_download_for_partial_run(self):
        run = make_run()
        EvaluationTurn.objects.create(
            run=run,
            turn_index=0,
            sample_label="Sample 1",
            model="gpt-a",
            status=TurnStatus.SUCCESS,
            response_text="partial",
        )
        response = Client().get(reverse("image_evaluator:download", kwargs={"run_id": run.id}))
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        self.assertIn(b"partial", response.content)

    def test_csv_redirects_when_no_turns(self):
        run = make_run()
        response = Client().get(reverse("image_evaluator:download", kwargs={"run_id": run.id}))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("image_evaluator:inspect", kwargs={"run_id": run.id}))


class PrepareUrlTests(TestCase):
    def test_prepare_at_new_path(self):
        response = Client().get(reverse("image_evaluator:prepare"))
        self.assertIn(response.status_code, (200, 503))

    def test_console_at_root(self):
        response = Client().get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Console")

    def test_pages_include_busy_overlay(self):
        response = Client().get("/")
        self.assertContains(response, 'id="busy-overlay"')
        self.assertContains(response, "busy-spinner")
