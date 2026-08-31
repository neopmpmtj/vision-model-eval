from io import BytesIO
from unittest.mock import MagicMock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse
from PIL import Image

from image_evaluator.forms import PrepareEvaluationForm
from image_evaluator.models import EvaluationRun
from image_evaluator.services.api_key import ApiKeyStatus
from image_evaluator.services.gemini_eval import GeminiApiRequestConfig, analyze_image as gemini_analyze_image
from image_evaluator.views import PrepareView


def make_test_image() -> SimpleUploadedFile:
    image = Image.new("RGB", (8, 8), color="red")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return SimpleUploadedFile("test.png", buffer.read(), content_type="image/png")


def mock_valid_api_key(*args, **kwargs):
    return ApiKeyStatus(ok=True, message="ok")


class MultiLabFormTests(TestCase):
    def test_google_api_defaults_snapshot(self):
        form = PrepareEvaluationForm(
            {
                "run_type": "latency_benchmark",
                "lab": "google",
                "prompt_preset": "describe",
                "models": ["gemini-3.6-flash", "gemini-3.5-flash"],
                "thinking_level": "high",
                "media_resolution": "medium",
                "gemini_max_output_tokens": "2048",
            },
            {"image": make_test_image()},
        )
        self.assertTrue(form.is_valid(), form.errors)
        defaults = form.api_defaults_dict()
        self.assertEqual(defaults["lab"], "google")
        self.assertEqual(defaults["thinking_level"], "high")
        self.assertEqual(defaults["media_resolution"], "medium")
        self.assertEqual(defaults["max_output_tokens"], 2048)
        self.assertNotIn("store", defaults)

    def test_deepseek_api_defaults_snapshot(self):
        form = PrepareEvaluationForm(
            {
                "run_type": "latency_benchmark",
                "lab": "deepseek",
                "prompt_preset": "describe",
                "models": ["deepseek-v4-flash-vision-exp"],
                "deepseek_reasoning_effort": "max",
                "deepseek_max_output_tokens": "900",
                "deepseek_image_detail": "low",
            },
            {"image": make_test_image()},
        )
        self.assertTrue(form.is_valid(), form.errors)
        defaults = form.api_defaults_dict()
        self.assertEqual(defaults["lab"], "deepseek")
        self.assertEqual(defaults["reasoning"]["effort"], "max")
        self.assertEqual(defaults["max_output_tokens"], 900)
        self.assertEqual(defaults["image_detail"], "low")
        self.assertNotIn("store", defaults)

    def test_single_model_allowed(self):
        form = PrepareEvaluationForm(
            {
                "run_type": "latency_benchmark",
                "lab": "deepseek",
                "prompt_preset": "describe",
                "models": ["deepseek-v4-flash-vision-exp"],
                "deepseek_reasoning_effort": "high",
                "deepseek_max_output_tokens": "1600",
                "deepseek_image_detail": "auto",
            },
            {"image": make_test_image()},
        )
        self.assertTrue(form.is_valid(), form.errors)

    @patch("image_evaluator.views.api_key_for_lab", return_value="test-gemini-key")
    @patch("image_evaluator.views.validate_lab_api_key", side_effect=mock_valid_api_key)
    def test_prepare_google_post(self, _mock_key, _mock_api_key):
        data = {
            "run_type": "latency_benchmark",
            "lab": "google",
            "prompt_preset": "describe",
            "models": ["gemini-3.6-flash", "gemini-3.5-flash"],
            "thinking_level": "medium",
            "media_resolution": "high",
            "gemini_max_output_tokens": "1600",
        }
        request = RequestFactory().post(reverse("image_evaluator:prepare"), data)
        request.FILES["image"] = make_test_image()
        request.session = {}
        response = PrepareView.as_view()(request)
        self.assertEqual(response.status_code, 302)
        run = EvaluationRun.objects.latest("created_at")
        self.assertEqual(run.api_defaults["lab"], "google")
        self.assertEqual(run.api_defaults["thinking_level"], "medium")


class GeminiThinkingSplitTests(TestCase):
    @patch("image_evaluator.services.gemini_eval.genai.Client")
    def test_gemini_25_sends_thinking_budget_only(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.text = "ok"
        mock_response.usage_metadata = None
        mock_response.response_id = "resp-1"
        mock_response.model_version = "gemini-2.5-flash"
        mock_client_cls.return_value.models.generate_content.return_value = mock_response

        image = make_test_image()
        image_path = image.temporary_file_path() if hasattr(image, "temporary_file_path") else None
        if image_path is None:
            from tempfile import NamedTemporaryFile

            with NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp.write(image.read())
                image_path = tmp.name

        config = GeminiApiRequestConfig(
            thinking_level="high",
            thinking_budget=512,
            media_resolution="high",
            max_output_tokens=100,
        )
        with patch("image_evaluator.services.gemini_eval.settings.GEMINI_API_KEY", "test-key"):
            gemini_analyze_image(
                model="gemini-2.5-flash",
                image_path=image_path,
                api_config=config,
            )

        call_kwargs = mock_client_cls.return_value.models.generate_content.call_args.kwargs
        thinking = call_kwargs["config"].thinking_config
        self.assertEqual(thinking.thinking_budget, 512)
        self.assertIsNone(thinking.thinking_level)

    @patch("image_evaluator.services.gemini_eval.genai.Client")
    def test_gemini_3_sends_thinking_level_only(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.text = "ok"
        mock_response.usage_metadata = None
        mock_response.response_id = "resp-2"
        mock_response.model_version = "gemini-3.6-flash"
        mock_client_cls.return_value.models.generate_content.return_value = mock_response

        from tempfile import NamedTemporaryFile

        image = make_test_image()
        with NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(image.read())
            image_path = tmp.name

        config = GeminiApiRequestConfig(
            thinking_level="low",
            thinking_budget=1024,
            media_resolution="high",
            max_output_tokens=100,
        )
        with patch("image_evaluator.services.gemini_eval.settings.GEMINI_API_KEY", "test-key"):
            gemini_analyze_image(
                model="gemini-3.6-flash",
                image_path=image_path,
                api_config=config,
            )

        call_kwargs = mock_client_cls.return_value.models.generate_content.call_args.kwargs
        thinking = call_kwargs["config"].thinking_config
        level = thinking.thinking_level
        if hasattr(level, "value"):
            level = level.value
        self.assertEqual(str(level).lower(), "low")
        self.assertIsNone(thinking.thinking_budget)


class LabKeyValidationTests(TestCase):
    @patch("image_evaluator.services.lab_api_key.OpenAI")
    def test_openai_validation_uses_openai_models_only(self, mock_openai):
        mock_openai.return_value.models.list.return_value = [MagicMock(id="gpt-5.6-luna")]
        from image_evaluator.services.lab_api_key import validate_openai_api_key

        status = validate_openai_api_key("sk-test")
        self.assertFalse(status.ok)
        self.assertTrue(any("gpt-5.6" in model for model in status.missing_models))
        self.assertFalse(any("gemini" in model for model in status.checked_models))

    def test_missing_gemini_key_shows_inline_alert_on_prepare(self):
        from django.test import Client

        with patch(
            "image_evaluator.services.lab_api_key.api_key_for_lab",
            side_effect=lambda lab_id: "" if lab_id == "google" else "present",
        ), patch(
            "image_evaluator.services.lab_api_key.validate_lab_api_key",
            return_value=ApiKeyStatus(ok=True, message="ok"),
        ):
            response = Client().get(reverse("image_evaluator:prepare"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "GEMINI_API_KEY was not found")
        self.assertContains(response, "lab-key-alert")


class LabKeyAlertTests(SimpleTestCase):
    def test_missing_key_alert(self):
        from image_evaluator.services.lab_api_key import lab_key_alert

        with patch("image_evaluator.services.lab_api_key.api_key_for_lab", return_value=""):
            alert = lab_key_alert("deepseek")
        self.assertFalse(alert["ok"])
        self.assertEqual(alert["status"], "missing")
        self.assertEqual(alert["setting_name"], "DEEPSEEK_API_KEY")
        self.assertIn("was not found", alert["headline"])

    @patch("image_evaluator.services.lab_api_key.validate_lab_api_key")
    @patch("image_evaluator.services.lab_api_key.api_key_for_lab", return_value="sk-test")
    def test_invalid_key_alert(self, _mock_key, mock_validate):
        from image_evaluator.services.lab_api_key import lab_key_alert

        mock_validate.return_value = ApiKeyStatus(
            ok=False,
            message="rejected",
            missing_models=["deepseek-v4-flash-vision-exp"],
        )
        alert = lab_key_alert("deepseek")
        self.assertFalse(alert["ok"])
        self.assertEqual(alert["status"], "invalid")
        self.assertEqual(alert["missing_models"], ["deepseek-v4-flash-vision-exp"])


class PrepareInlineKeyAlertTests(TestCase):
    @patch("image_evaluator.services.lab_api_key.api_key_for_lab")
    def test_prepare_page_embeds_lab_key_alerts(self, mock_key_for_lab):
        from django.test import Client

        def key_for_lab(lab_id):
            return "" if lab_id == "deepseek" else "present"

        mock_key_for_lab.side_effect = key_for_lab

        with patch(
            "image_evaluator.services.lab_api_key.validate_lab_api_key",
            return_value=ApiKeyStatus(ok=True, message="ok"),
        ):
            response = Client().get(reverse("image_evaluator:prepare"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "lab-key-alerts")
        self.assertContains(response, "DEEPSEEK_API_KEY was not found")
        self.assertContains(response, "lab-key-alert")

    @patch("image_evaluator.services.lab_api_key.api_key_for_lab", return_value="")
    def test_prepare_deepseek_missing_in_json(self, _mock_key):
        import json
        import re

        from django.test import Client

        response = Client().get(reverse("image_evaluator:prepare"))
        match = re.search(
            r'<script id="lab-key-alerts" type="application/json">(.*?)</script>',
            response.content.decode(),
            re.DOTALL,
        )
        self.assertIsNotNone(match)
        alerts = json.loads(match.group(1))
        self.assertFalse(alerts["deepseek"]["ok"])
        self.assertEqual(alerts["deepseek"]["status"], "missing")
