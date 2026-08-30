from io import BytesIO
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse
from PIL import Image

from image_evaluator.models import EvaluationRun, EvaluationTurn, TurnStatus
from image_evaluator.prompt_presets import preset_texts
from image_evaluator.services.api_key import ApiKeyStatus
from image_evaluator.views import PrepareView


def make_test_image() -> SimpleUploadedFile:
    image = Image.new("RGB", (8, 8), color="red")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return SimpleUploadedFile("test.png", buffer.read(), content_type="image/png")


def mock_valid_api_key(*args, **kwargs):
    return ApiKeyStatus(ok=True, message="ok")


def base_prepare_data(**overrides):
    data = {
        "run_type": "blind_comparison",
        "lab": "openai",
        "prompt_preset": "describe",
        "prompt": "describe",
        "models": ["gpt-5.6-luna", "gpt-5.6-terra"],
        "reasoning_effort": "low",
        "reasoning_mode": "standard",
        "max_output_tokens": "1600",
        "image_detail": "auto",
    }
    data.update(overrides)
    return data


class PromptPresetTests(TestCase):
    @patch("image_evaluator.views.validate_api_key", side_effect=mock_valid_api_key)
    def test_prepare_page_shows_preset_labels(self, _mock_key):
        response = Client().get(reverse("image_evaluator:prepare"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Prompt preset")
        self.assertContains(response, "Describe (default)")
        self.assertContains(response, "OCR / text extraction")
        self.assertContains(response, "prompt-preset-texts")

    @patch("image_evaluator.views.validate_api_key", side_effect=mock_valid_api_key)
    def test_custom_prompt_text_persisted_not_preset_body(self, _mock_key):
        custom_prompt = "Only count red objects."
        data = base_prepare_data(
            prompt_preset="ocr",
            prompt=custom_prompt,
        )
        request = RequestFactory().post(reverse("image_evaluator:prepare"), data)
        request.FILES["image"] = make_test_image()
        request.session = {}
        response = PrepareView.as_view()(request)
        self.assertEqual(response.status_code, 302)
        run = EvaluationRun.objects.latest("created_at")
        self.assertEqual(run.prompt, custom_prompt)
        self.assertNotEqual(run.prompt, preset_texts()["ocr"])

    @patch("image_evaluator.views.validate_api_key", side_effect=mock_valid_api_key)
    def test_omitted_description_defaults_to_blank(self, _mock_key):
        data = base_prepare_data()
        request = RequestFactory().post(reverse("image_evaluator:prepare"), data)
        request.FILES["image"] = make_test_image()
        request.session = {}
        response = PrepareView.as_view()(request)
        self.assertEqual(response.status_code, 302)
        run = EvaluationRun.objects.latest("created_at")
        self.assertEqual(run.description, "")

    @patch("image_evaluator.views.validate_api_key", side_effect=mock_valid_api_key)
    def test_description_persisted_and_shown_on_inspect(self, _mock_key):
        description = "OCR on faded shipping labels"
        data = base_prepare_data(description=description)
        request = RequestFactory().post(reverse("image_evaluator:prepare"), data)
        request.FILES["image"] = make_test_image()
        request.session = {}
        response = PrepareView.as_view()(request)
        self.assertEqual(response.status_code, 302)
        run = EvaluationRun.objects.latest("created_at")
        self.assertEqual(run.description, description)

        inspect = Client().get(reverse("image_evaluator:inspect", kwargs={"run_id": run.id}))
        self.assertContains(inspect, description)

    @patch("image_evaluator.views.validate_api_key", side_effect=mock_valid_api_key)
    def test_csv_includes_session_description(self, _mock_key):
        description = "Compare terra vs sol on receipts"
        data = base_prepare_data(description=description)
        request = RequestFactory().post(reverse("image_evaluator:prepare"), data)
        request.FILES["image"] = make_test_image()
        request.session = {}
        PrepareView.as_view()(request)
        run = EvaluationRun.objects.latest("created_at")
        EvaluationTurn.objects.create(
            run=run,
            turn_index=0,
            sample_label="Sample 1",
            model="gpt-5.6-luna",
            status=TurnStatus.SUCCESS,
            response_text="ok",
        )
        response = Client().get(reverse("image_evaluator:download", kwargs={"run_id": run.id}))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertIn("session_description", content)
        self.assertIn(description, content)
