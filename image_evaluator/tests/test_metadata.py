from datetime import datetime, timezone
from io import BytesIO
from unittest.mock import MagicMock, patch

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
from image_evaluator.services.openai_eval import AnalysisResult, ApiRequestConfig, _response_snapshot


def make_test_image() -> SimpleUploadedFile:
    image = Image.new("RGB", (8, 8), color="red")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return SimpleUploadedFile("test.png", buffer.read(), content_type="image/png")


def make_analysis_result() -> AnalysisResult:
    now = datetime.now(timezone.utc)
    return AnalysisResult(
        response_text="ok",
        request_started_at=now,
        request_finished_at=now,
        latency_wall_seconds=1.234,
        latency_openai_seconds=1.1,
        input_tokens=10,
        output_tokens=5,
        total_tokens=15,
        reasoning_tokens=2,
        cached_tokens=1,
        cache_write_tokens=0,
        usage_raw={"input_tokens": 10},
        api_request={"model": "gpt-test", "reasoning": {"effort": "low"}},
        api_response={"id": "resp_123", "status": "completed"},
        openai_response_id="resp_123",
        response_model="gpt-test",
        openai_status="completed",
    )


class MetadataExtractionTests(TestCase):
    def test_response_snapshot(self):
        response = MagicMock()
        response.id = "resp_abc"
        response.model = "gpt-test"
        response.status = "completed"
        response.created_at = 1.0
        response.completed_at = 2.5
        response.max_output_tokens = 16
        response.model_dump.return_value = {"reasoning": {"effort": "low"}, "usage": {"input_tokens": 3}}

        snapshot = _response_snapshot(response)
        self.assertEqual(snapshot["id"], "resp_abc")
        self.assertEqual(snapshot["model"], "gpt-test")


from image_evaluator.services.api_key import ApiKeyStatus


def mock_valid_api_key(*args, **kwargs):
    return ApiKeyStatus(ok=True, message="ok")


class TurnPersistenceTests(TestCase):
    def setUp(self):
        self.run = EvaluationRun.objects.create(
            image=make_test_image(),
            image_name="test.png",
            image_content_type="image/png",
            image_size_bytes=100,
            image_width=8,
            image_height=8,
            prompt="describe",
            model_order=["gpt-a", "gpt-b"],
            api_defaults=ApiRequestConfig.from_settings().to_dict(),
        )

    @patch("image_evaluator.views.validate_api_key", side_effect=mock_valid_api_key)
    @patch("image_evaluator.views.analyze_image")
    def test_generate_persists_turn_before_rating(self, mock_analyze, _mock_key):
        mock_analyze.return_value = make_analysis_result()
        client = Client()
        url = reverse("image_evaluator:evaluate", kwargs={"run_id": self.run.id})
        response = client.post(url, {"action": "generate"})
        self.assertEqual(response.status_code, 302)
        turn = EvaluationTurn.objects.get(run=self.run, turn_index=0)
        self.assertEqual(turn.status, TurnStatus.SUCCESS)
        self.assertEqual(turn.latency_wall_seconds, 1.234)
        self.assertIsNone(turn.rating)

    @patch("image_evaluator.views.validate_api_key", side_effect=mock_valid_api_key)
    @patch("image_evaluator.views.analyze_image")
    def test_error_turn_persisted(self, mock_analyze, _mock_key):
        mock_analyze.side_effect = RuntimeError("api failed")
        client = Client()
        url = reverse("image_evaluator:evaluate", kwargs={"run_id": self.run.id})
        client.post(url, {"action": "generate"})
        turn = EvaluationTurn.objects.get(run=self.run, turn_index=0)
        self.assertEqual(turn.status, TurnStatus.ERROR)
        self.assertIn("api failed", turn.error_message)


class BenchmarkViewTests(TestCase):
    @patch("image_evaluator.views.validate_api_key", side_effect=mock_valid_api_key)
    @patch("image_evaluator.views.analyze_image")
    def test_benchmark_creates_turns_and_latency_benchmark(self, mock_analyze, _mock_key):
        mock_analyze.return_value = make_analysis_result()
        run = EvaluationRun.objects.create(
            image=make_test_image(),
            image_name="test.png",
            image_content_type="image/png",
            prompt="describe",
            model_order=["gpt-a", "gpt-b"],
        )
        LatencyBenchmark.objects.create(run=run, turn_count_expected=2)
        client = Client()
        url = reverse("image_evaluator:benchmark", kwargs={"run_id": run.id})
        response = client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(EvaluationTurn.objects.filter(run=run).count(), 2)
        benchmark = LatencyBenchmark.objects.get(run=run)
        self.assertEqual(benchmark.status, RunStatus.COMPLETED)
        self.assertEqual(benchmark.successful_turn_count, 2)
