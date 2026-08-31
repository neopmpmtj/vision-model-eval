from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, tag
from openai import APIConnectionError, AuthenticationError, RateLimitError

from image_evaluator.model_catalog import models_for_lab
from image_evaluator.services.lab_api_key import (
    run_deepseek_billable_probe,
    run_gemini_billable_probe,
    run_lab_billable_probe,
    validate_deepseek_api_key,
    validate_gemini_api_key,
    validate_lab_api_key,
)


class GeminiValidateUnitTests(SimpleTestCase):
    def test_empty_key_is_invalid(self):
        status = validate_gemini_api_key("")
        self.assertFalse(status.ok)
        self.assertIn("not set", status.message)

    @patch("image_evaluator.services.lab_api_key.genai.Client")
    def test_missing_configured_models(self, mock_client_cls):
        mock_client_cls.return_value.models.list.return_value = [
            MagicMock(name="models/other-model"),
        ]
        mock_client_cls.return_value.models.list.return_value[0].name = "models/other-model"
        status = validate_gemini_api_key("gemini-test-key")
        self.assertFalse(status.ok)
        self.assertEqual(status.missing_models, list(models_for_lab("google")))


class DeepSeekValidateUnitTests(SimpleTestCase):
    def test_empty_key_is_invalid(self):
        status = validate_deepseek_api_key("")
        self.assertFalse(status.ok)
        self.assertIn("not set", status.message)

    @patch("image_evaluator.services.lab_api_key.OpenAI")
    def test_missing_configured_models(self, mock_openai):
        mock_openai.return_value.models.list.return_value = [
            MagicMock(id="other-model"),
        ]
        status = validate_deepseek_api_key("ds-test")
        self.assertFalse(status.ok)
        self.assertEqual(status.missing_models, list(models_for_lab("deepseek")))


class GeminiBillableProbeUnitTests(SimpleTestCase):
    def test_empty_key_is_invalid(self):
        status = run_gemini_billable_probe(api_key="")
        self.assertFalse(status.ok)
        self.assertIn("not set", status.message)

    @patch("image_evaluator.services.lab_api_key.genai.Client")
    def test_resource_exhausted_maps_to_quota_message(self, mock_client_cls):
        mock_client_cls.return_value.models.generate_content.side_effect = Exception(
            "429 RESOURCE_EXHAUSTED. You exceeded your current quota."
        )
        status = run_gemini_billable_probe(api_key="gemini-test-key")
        self.assertFalse(status.ok)
        self.assertIn("insufficient quota or credits", status.message.lower())
        self.assertIn("google gemini", status.message.lower())

    @patch("image_evaluator.services.lab_api_key.genai.Client")
    def test_successful_probe(self, mock_client_cls):
        usage = MagicMock(prompt_token_count=8, candidates_token_count=2)
        mock_client_cls.return_value.models.generate_content.return_value = MagicMock(
            usage_metadata=usage
        )
        status = run_gemini_billable_probe(api_key="gemini-test-key")
        self.assertTrue(status.ok)
        self.assertEqual(status.input_tokens, 8)
        self.assertEqual(status.output_tokens, 2)


class DeepSeekBillableProbeUnitTests(SimpleTestCase):
    def test_empty_key_is_invalid(self):
        status = run_deepseek_billable_probe(api_key="")
        self.assertFalse(status.ok)
        self.assertIn("not set", status.message)

    @patch("image_evaluator.services.lab_api_key.OpenAI")
    def test_insufficient_quota(self, mock_openai):
        mock_openai.return_value.responses.create.side_effect = RateLimitError(
            "insufficient_quota",
            response=MagicMock(),
            body={"error": {"code": "insufficient_quota"}},
        )
        status = run_deepseek_billable_probe(api_key="ds-test")
        self.assertFalse(status.ok)
        self.assertIn("insufficient quota or credits", status.message.lower())
        self.assertIn("deepseek", status.message.lower())

    @patch("image_evaluator.services.lab_api_key.OpenAI")
    def test_successful_probe(self, mock_openai):
        usage = MagicMock(input_tokens=12, output_tokens=3)
        mock_openai.return_value.responses.create.return_value = MagicMock(usage=usage)
        status = run_deepseek_billable_probe(api_key="ds-test")
        self.assertTrue(status.ok)
        self.assertEqual(status.input_tokens, 12)
        self.assertEqual(status.output_tokens, 3)


class LabBillableProbeDispatchTests(SimpleTestCase):
    @patch("image_evaluator.services.lab_api_key.run_gemini_billable_probe")
    def test_dispatch_google(self, mock_probe):
        mock_probe.return_value = MagicMock(ok=True, message="ok")
        run_lab_billable_probe(lab_id="google")
        mock_probe.assert_called_once()

    @patch("image_evaluator.services.lab_api_key.run_deepseek_billable_probe")
    def test_dispatch_deepseek(self, mock_probe):
        mock_probe.return_value = MagicMock(ok=True, message="ok")
        run_lab_billable_probe(lab_id="deepseek")
        mock_probe.assert_called_once()


class ValidateLabDispatchTests(SimpleTestCase):
    def test_unknown_lab_falls_back_to_openai_validator(self):
        with patch(
            "image_evaluator.services.lab_api_key.validate_openai_api_key",
            return_value=MagicMock(ok=True, message="ok"),
        ) as mock_openai:
            status = validate_lab_api_key("openai")
            mock_openai.assert_called_once()
            self.assertTrue(status.ok)


@tag("gemini")
class GeminiLiveTests(SimpleTestCase):
    """Live Gemini checks. Run with: python manage.py test image_evaluator.tests.test_lab_probes --tag=gemini"""

    def test_api_key_valid(self):
        status = validate_gemini_api_key()
        self.assertTrue(status.ok, status.message)
        self.assertEqual(status.missing_models, [])

    def test_billable_probe(self):
        status = run_gemini_billable_probe()
        self.assertTrue(status.ok, status.message)
        self.assertTrue(status.model)


@tag("deepseek")
class DeepSeekLiveTests(SimpleTestCase):
    """Live DeepSeek checks. Run with: python manage.py test image_evaluator.tests.test_lab_probes --tag=deepseek"""

    def test_api_key_valid(self):
        status = validate_deepseek_api_key()
        self.assertTrue(status.ok, status.message)
        self.assertEqual(status.missing_models, [])

    def test_billable_probe(self):
        status = run_deepseek_billable_probe()
        self.assertTrue(status.ok, status.message)
        self.assertTrue(status.model)
