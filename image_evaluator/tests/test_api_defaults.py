from io import BytesIO
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse
from PIL import Image

from image_evaluator.forms import PrepareEvaluationForm
from image_evaluator.models import EvaluationRun
from image_evaluator.services.api_key import ApiKeyStatus
from image_evaluator.services.openai_eval import ApiRequestConfig
from image_evaluator.views import PrepareView


def make_test_image() -> SimpleUploadedFile:
    image = Image.new("RGB", (8, 8), color="red")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return SimpleUploadedFile("test.png", buffer.read(), content_type="image/png")


def mock_valid_api_key(*args, **kwargs):
    return ApiKeyStatus(ok=True, message="ok")


class ApiDefaultsFormTests(TestCase):
    @patch("image_evaluator.views.validate_api_key", side_effect=mock_valid_api_key)
    def test_prepare_snapshots_api_defaults_on_run(self, _mock_key):
        data = {
            "run_type": "blind_comparison",
            "lab": "openai",
            "prompt": "describe",
            "models": ["gpt-5.6-luna", "gpt-5.6-terra"],
            "reasoning_effort": "xhigh",
            "reasoning_mode": "pro",
            "max_output_tokens": "2048",
            "image_detail": "high",
            "store": "on",
        }
        request = RequestFactory().post(reverse("image_evaluator:prepare"), data)
        request.FILES["image"] = make_test_image()
        request.session = {}
        response = PrepareView.as_view()(request)
        self.assertEqual(response.status_code, 302)
        run = EvaluationRun.objects.latest("created_at")
        self.assertEqual(run.api_defaults["lab"], "openai")
        self.assertEqual(run.api_defaults["reasoning"]["effort"], "xhigh")
        self.assertEqual(run.api_defaults["reasoning"]["mode"], "pro")
        self.assertEqual(run.api_defaults["max_output_tokens"], 2048)
        self.assertEqual(run.api_defaults["image_detail"], "high")
        self.assertTrue(run.api_defaults["store"])

    def test_form_api_defaults_dict(self):
        form = PrepareEvaluationForm(
            {
                "run_type": "blind_comparison",
                "lab": "openai",
                "prompt": "describe",
                "models": ["gpt-5.6-luna", "gpt-5.6-terra"],
                "reasoning_effort": "minimal",
                "reasoning_mode": "standard",
                "max_output_tokens": "512",
                "image_detail": "original",
            },
            {"image": make_test_image()},
        )
        self.assertTrue(form.is_valid(), form.errors)
        defaults = form.api_defaults_dict()
        self.assertEqual(defaults["reasoning"]["effort"], "minimal")
        self.assertEqual(defaults["image_detail"], "original")


class ApiConfigFromDictTests(TestCase):
    def test_from_dict_reads_reasoning_mode(self):
        config = ApiRequestConfig.from_dict(
            {
                "lab": "openai",
                "reasoning": {"effort": "high", "mode": "pro"},
                "max_output_tokens": 900,
                "store": False,
                "image_detail": "original",
            }
        )
        self.assertEqual(config.reasoning_effort, "high")
        self.assertEqual(config.reasoning_mode, "pro")
        self.assertEqual(config.max_output_tokens, 900)
        self.assertEqual(config.image_detail, "original")


class GenerateUsesRunSnapshotTests(TestCase):
    def setUp(self):
        self.run = EvaluationRun.objects.create(
            image=make_test_image(),
            image_name="test.png",
            image_content_type="image/png",
            prompt="describe",
            model_order=["gpt-a", "gpt-b"],
            api_defaults={
                "lab": "openai",
                "reasoning": {"effort": "xhigh", "mode": "pro"},
                "max_output_tokens": 2048,
                "store": False,
                "image_detail": "high",
            },
        )

    @patch("image_evaluator.views.validate_api_key", side_effect=mock_valid_api_key)
    @patch("image_evaluator.views.analyze_image")
    def test_generate_passes_run_api_config(self, mock_analyze, _mock_key):
        from datetime import datetime, timezone

        from image_evaluator.services.openai_eval import AnalysisResult

        mock_analyze.return_value = AnalysisResult(
            response_text="ok",
            request_started_at=datetime.now(timezone.utc),
            request_finished_at=datetime.now(timezone.utc),
            latency_wall_seconds=1.0,
            latency_openai_seconds=1.0,
            input_tokens=1,
            output_tokens=1,
            total_tokens=2,
            reasoning_tokens=0,
            cached_tokens=0,
            cache_write_tokens=0,
            usage_raw={},
            api_request={},
            api_response={},
            openai_response_id="r1",
            response_model="gpt-a",
            openai_status="completed",
        )
        client = Client()
        url = reverse("image_evaluator:evaluate", kwargs={"run_id": self.run.id})
        client.post(url, {"action": "generate"})
        mock_analyze.assert_called_once()
        config = mock_analyze.call_args.kwargs["api_config"]
        self.assertEqual(config.reasoning_effort, "xhigh")
        self.assertEqual(config.reasoning_mode, "pro")
        self.assertEqual(config.max_output_tokens, 2048)
        self.assertEqual(config.image_detail, "high")
