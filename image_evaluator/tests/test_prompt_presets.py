from io import BytesIO
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse
from PIL import Image

from image_evaluator.models import EvaluationRun, EvaluationTurn, TurnStatus
from image_evaluator.prompt_presets import (
    ComposeEvalTextError,
    compose_eval_text,
    preset_texts,
)
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
        "models": ["gpt-5.6-luna", "gpt-5.6-terra"],
        "reasoning_effort": "low",
        "reasoning_mode": "standard",
        "max_output_tokens": "1600",
        "image_detail": "auto",
    }
    data.update(overrides)
    return data


class ComposeEvalTextTests(TestCase):
    def test_default_preset_image_only_user_prompt(self):
        instructions, user_prompt = compose_eval_text(
            omit_instructions=False,
            preset_id="describe",
            additional="",
        )
        self.assertEqual(instructions, preset_texts()["describe"])
        self.assertEqual(user_prompt, "")

    def test_appends_additional_to_preset(self):
        instructions, user_prompt = compose_eval_text(
            omit_instructions=False,
            preset_id="ocr",
            additional="Focus on the license plate.",
        )
        self.assertTrue(instructions.startswith(preset_texts()["ocr"]))
        self.assertIn("Focus on the license plate.", instructions)
        self.assertEqual(user_prompt, "")

    def test_omit_sends_additional_as_user_prompt(self):
        instructions, user_prompt = compose_eval_text(
            omit_instructions=True,
            preset_id="describe",
            additional="Is there a stop sign? Answer yes or no.",
        )
        self.assertEqual(instructions, "")
        self.assertEqual(user_prompt, "Is there a stop sign? Answer yes or no.")

    def test_omit_requires_additional(self):
        with self.assertRaises(ComposeEvalTextError):
            compose_eval_text(omit_instructions=True, preset_id="describe", additional="  ")


class PromptPresetTests(TestCase):
    @patch("image_evaluator.views.validate_api_key", side_effect=mock_valid_api_key)
    def test_prepare_page_shows_system_instruction_controls(self, _mock_key):
        response = Client().get(reverse("image_evaluator:prepare"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "System instructions")
        self.assertContains(response, "Omit system instructions")
        self.assertContains(response, "Describe (default)")
        self.assertContains(response, "OCR / text extraction")
        self.assertNotContains(response, ">Custom<")

    @patch("image_evaluator.views.validate_api_key", side_effect=mock_valid_api_key)
    def test_default_describe_persists_as_instructions(self, _mock_key):
        request = RequestFactory().post(reverse("image_evaluator:prepare"), base_prepare_data())
        request.FILES["image"] = make_test_image()
        request.session = {}
        response = PrepareView.as_view()(request)
        self.assertEqual(response.status_code, 302)
        run = EvaluationRun.objects.latest("created_at")
        self.assertEqual(run.instructions, preset_texts()["describe"])
        self.assertEqual(run.user_prompt, "")
        self.assertFalse(run.api_defaults["omit_instructions"])
        self.assertEqual(run.api_defaults["prompt_preset"], "describe")

    @patch("image_evaluator.views.validate_api_key", side_effect=mock_valid_api_key)
    def test_omit_persists_user_prompt_only(self, _mock_key):
        additional = "Is there a cat? Answer yes or no."
        data = base_prepare_data(omit_instructions="on", additional=additional)
        request = RequestFactory().post(reverse("image_evaluator:prepare"), data)
        request.FILES["image"] = make_test_image()
        request.session = {}
        response = PrepareView.as_view()(request)
        self.assertEqual(response.status_code, 302)
        run = EvaluationRun.objects.latest("created_at")
        self.assertEqual(run.instructions, "")
        self.assertEqual(run.user_prompt, additional)
        self.assertTrue(run.api_defaults["omit_instructions"])

        inspect = Client().get(reverse("image_evaluator:inspect", kwargs={"run_id": run.id}))
        self.assertContains(inspect, additional)
        self.assertContains(inspect, "User prompt")

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
    def test_csv_includes_instructions_and_user_prompt(self, _mock_key):
        description = "Compare terra vs sol on receipts"
        additional = "Is there a stop sign?"
        data = base_prepare_data(description=description, omit_instructions="on", additional=additional)
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
        self.assertIn("instructions", content)
        self.assertIn("user_prompt", content)
        self.assertIn(additional, content)
