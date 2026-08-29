from unittest.mock import MagicMock, patch

from django.conf import settings
from django.test import SimpleTestCase, tag
from openai import APIConnectionError, AuthenticationError, RateLimitError

from image_evaluator.services.api_key import run_billable_probe, validate_api_key


class ValidateApiKeyUnitTests(SimpleTestCase):
    def test_empty_key_is_invalid(self):
        status = validate_api_key("")
        self.assertFalse(status.ok)
        self.assertIn("not set", status.message)

    @patch("image_evaluator.services.api_key._client")
    def test_authentication_error_is_invalid(self, mock_client):
        mock_client.return_value.models.list.side_effect = AuthenticationError(
            "invalid", response=MagicMock(), body=None
        )
        status = validate_api_key("sk-test")
        self.assertFalse(status.ok)
        self.assertIn("rejected", status.message.lower())

    @patch("image_evaluator.services.api_key._client")
    def test_missing_configured_models(self, mock_client):
        mock_client.return_value.models.list.return_value = [
            MagicMock(id="other-model"),
        ]
        status = validate_api_key("sk-test")
        self.assertFalse(status.ok)
        self.assertEqual(status.missing_models, list(settings.AVAILABLE_MODELS))

    @patch("image_evaluator.services.api_key._client")
    def test_all_models_present(self, mock_client):
        mock_client.return_value.models.list.return_value = [
            MagicMock(id=model) for model in settings.AVAILABLE_MODELS
        ]
        status = validate_api_key("sk-test")
        self.assertTrue(status.ok)

    @patch("image_evaluator.services.api_key._client")
    def test_connection_error(self, mock_client):
        mock_client.return_value.models.list.side_effect = APIConnectionError(request=MagicMock())
        status = validate_api_key("sk-test")
        self.assertFalse(status.ok)
        self.assertIn("reach OpenAI", status.message)


class BillableProbeUnitTests(SimpleTestCase):
    def test_empty_key_is_invalid(self):
        status = run_billable_probe(api_key="")
        self.assertFalse(status.ok)
        self.assertIn("not set", status.message)

    @patch("image_evaluator.services.api_key._client")
    def test_insufficient_quota(self, mock_client):
        mock_client.return_value.responses.create.side_effect = RateLimitError(
            "insufficient_quota",
            response=MagicMock(),
            body={"error": {"code": "insufficient_quota"}},
        )
        status = run_billable_probe(api_key="sk-test")
        self.assertFalse(status.ok)
        self.assertIn("insufficient quota", status.message.lower())

    @patch("image_evaluator.services.api_key._client")
    def test_successful_probe(self, mock_client):
        usage = MagicMock(input_tokens=10, output_tokens=2)
        mock_client.return_value.responses.create.return_value = MagicMock(usage=usage)
        status = run_billable_probe(api_key="sk-test")
        self.assertTrue(status.ok)
        self.assertEqual(status.input_tokens, 10)
        self.assertEqual(status.output_tokens, 2)


@tag("openai")
class OpenAILiveTests(SimpleTestCase):
    """Live OpenAI checks. Run with: python manage.py test image_evaluator.tests.test_api_key --tag=openai"""

    def test_api_key_valid(self):
        status = validate_api_key()
        self.assertTrue(status.ok, status.message)
        self.assertEqual(status.missing_models, [])

    def test_billable_probe(self):
        status = run_billable_probe()
        self.assertTrue(status.ok, status.message)
        self.assertTrue(status.model)
