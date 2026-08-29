"""OpenAI vision evaluation helpers extracted from the Streamlit prototype."""

from __future__ import annotations

import base64
import random
import time
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from openai import OpenAI


@dataclass(frozen=True)
class AnalysisResult:
    response_text: str
    latency_seconds: float
    input_tokens: int | None
    output_tokens: int | None


def shuffle_models(selected_models: list[str]) -> list[str]:
    model_order = list(selected_models)
    random.SystemRandom().shuffle(model_order)
    return model_order


def analyze_image(
    *,
    model: str,
    prompt: str,
    image_path: Path | str,
    image_content_type: str = "image/jpeg",
) -> AnalysisResult:
    image_bytes = Path(image_path).read_bytes()
    encoded_image = base64.b64encode(image_bytes).decode("utf-8")
    image_data_url = f"data:{image_content_type};base64,{encoded_image}"

    client = OpenAI(api_key=settings.OPENAI_API_KEY)

    started_at = time.perf_counter()
    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {
                        "type": "input_image",
                        "image_url": image_data_url,
                        "detail": "auto",
                    },
                ],
            }
        ],
        reasoning={"effort": "low"},
        max_output_tokens=1600,
        store=False,
    )
    latency_seconds = round(time.perf_counter() - started_at, 3)
    usage = getattr(response, "usage", None)

    return AnalysisResult(
        response_text=response.output_text,
        latency_seconds=latency_seconds,
        input_tokens=getattr(usage, "input_tokens", None),
        output_tokens=getattr(usage, "output_tokens", None),
    )
