import base64
import csv
import io
import os
import random
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI


APP_DIR = Path(__file__).resolve().parent
RESULTS_FILE = APP_DIR / "results.csv"
MODELS = [
    "gpt-5.6-luna",
    "gpt-5.6-terra",
    "gpt-5.6-sol",
]
CSV_FIELDS = [
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


load_dotenv(APP_DIR / ".env")
st.set_page_config(page_title="OpenAI Image Evaluator", page_icon="👁️", layout="wide")


def initialize_state() -> None:
    defaults = {
        "started": False,
        "run_id": None,
        "model_order": [],
        "current_index": 0,
        "current_response": None,
        "current_latency": None,
        "current_input_tokens": None,
        "current_output_tokens": None,
        "results": [],
        "image_bytes": None,
        "image_name": None,
        "image_type": None,
        "frozen_prompt": None,
        "request_error": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset_evaluation() -> None:
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()


def begin_evaluation(uploaded_file, prompt: str, selected_models: list[str]) -> None:
    model_order = selected_models.copy()
    random.SystemRandom().shuffle(model_order)
    st.session_state.started = True
    st.session_state.run_id = str(uuid.uuid4())
    st.session_state.model_order = model_order
    st.session_state.current_index = 0
    st.session_state.current_response = None
    st.session_state.current_latency = None
    st.session_state.current_input_tokens = None
    st.session_state.current_output_tokens = None
    st.session_state.results = []
    st.session_state.image_bytes = uploaded_file.getvalue()
    st.session_state.image_name = uploaded_file.name
    st.session_state.image_type = uploaded_file.type or "image/jpeg"
    st.session_state.frozen_prompt = prompt.strip()
    st.session_state.request_error = None


def analyze_image(model: str) -> None:
    encoded_image = base64.b64encode(st.session_state.image_bytes).decode("utf-8")
    image_data_url = f"data:{st.session_state.image_type};base64,{encoded_image}"
    client = OpenAI()

    started_at = time.perf_counter()
    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": st.session_state.frozen_prompt},
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
    st.session_state.current_latency = round(time.perf_counter() - started_at, 3)
    st.session_state.current_response = response.output_text
    usage = getattr(response, "usage", None)
    st.session_state.current_input_tokens = getattr(usage, "input_tokens", None)
    st.session_state.current_output_tokens = getattr(usage, "output_tokens", None)
    st.session_state.request_error = None


def append_result(result: dict) -> None:
    file_exists = RESULTS_FILE.exists()
    with RESULTS_FILE.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerow({field: result.get(field) for field in CSV_FIELDS})


def save_rating(rating: int, notes: str) -> None:
    index = st.session_state.current_index
    model = st.session_state.model_order[index]
    result = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "run_id": st.session_state.run_id,
        "sample": f"Sample {index + 1}",
        "model": model,
        "image_name": st.session_state.image_name,
        "prompt": st.session_state.frozen_prompt,
        "rating": rating,
        "notes": notes.strip(),
        "latency_seconds": st.session_state.current_latency,
        "input_tokens": st.session_state.current_input_tokens,
        "output_tokens": st.session_state.current_output_tokens,
        "response": st.session_state.current_response,
    }
    st.session_state.results.append(result)
    append_result(result)
    st.session_state.current_index += 1
    st.session_state.current_response = None
    st.session_state.current_latency = None
    st.session_state.current_input_tokens = None
    st.session_state.current_output_tokens = None
    st.session_state.request_error = None
    st.rerun()


initialize_state()

st.title("OpenAI Image Understanding Evaluator")
st.caption("One image · one fixed prompt · several OpenAI models · your blind ratings")

if not os.getenv("OPENAI_API_KEY"):
    st.error("OPENAI_API_KEY was not found. Run ./set_api_key.sh in the project folder, then restart the app.")
    st.stop()

if not st.session_state.started:
    st.subheader("Prepare a comparison")
    uploaded = st.file_uploader(
        "Upload one image",
        type=["png", "jpg", "jpeg", "webp", "gif"],
        accept_multiple_files=False,
    )
    prompt = st.text_area(
        "Prompt used for every model",
        value="Describe this image carefully. Identify the main objects, their relationships, any visible text, and anything uncertain.",
        height=120,
    )
    selected_models = st.multiselect(
        "Models to compare",
        MODELS,
        default=MODELS,
        help="Their order will be randomized and their identities hidden until you finish rating.",
    )

    if uploaded is not None:
        st.image(uploaded, caption=uploaded.name, width=500)

    can_start = uploaded is not None and bool(prompt.strip()) and len(selected_models) >= 2
    if st.button("Start blind comparison", type="primary", disabled=not can_start):
        begin_evaluation(uploaded, prompt, selected_models)
        st.rerun()

    if len(selected_models) < 2:
        st.info("Select at least two models to make a comparison.")
    st.stop()

total_models = len(st.session_state.model_order)
current_index = st.session_state.current_index

with st.sidebar:
    st.subheader("Fixed test inputs")
    st.image(st.session_state.image_bytes, caption=st.session_state.image_name)
    st.write(st.session_state.frozen_prompt)
    st.divider()
    if st.button("Reset evaluation"):
        reset_evaluation()

if current_index < total_models:
    sample_name = f"Sample {current_index + 1}"
    st.progress(current_index / total_models, text=f"{sample_name} of {total_models}")
    st.subheader(sample_name)
    st.caption("The model identity remains hidden until all responses have been rated.")

    if st.session_state.current_response is None:
        if st.button(f"Generate {sample_name}", type="primary"):
            try:
                with st.spinner("Analyzing the image…"):
                    analyze_image(st.session_state.model_order[current_index])
                st.rerun()
            except Exception as exc:
                st.session_state.request_error = str(exc)

        if st.session_state.request_error:
            st.error("The request failed. Check your API access, credit, connection, and model availability.")
            with st.expander("Technical details"):
                st.code(st.session_state.request_error)
        st.stop()

    st.markdown("### Response")
    st.write(st.session_state.current_response)
    st.caption(f"Response time: {st.session_state.current_latency:.3f} seconds")

    with st.form(f"rating_form_{current_index}"):
        rating = st.slider("Your rating", min_value=1, max_value=5, value=3)
        notes = st.text_area("Optional notes", placeholder="What was correct, missed, vague, or especially useful?")
        submitted = st.form_submit_button("Save rating and continue", type="primary")
        if submitted:
            save_rating(rating, notes)
else:
    st.success("Comparison complete — model identities are now revealed.")
    results_df = pd.DataFrame(st.session_state.results)
    display_columns = [
        "sample",
        "model",
        "rating",
        "latency_seconds",
        "input_tokens",
        "output_tokens",
        "notes",
        "response",
    ]
    st.dataframe(results_df[display_columns], use_container_width=True, hide_index=True)

    csv_buffer = io.StringIO()
    results_df.to_csv(csv_buffer, index=False)
    st.download_button(
        "Download this comparison as CSV",
        data=csv_buffer.getvalue(),
        file_name=f"image-comparison-{st.session_state.run_id}.csv",
        mime="text/csv",
    )

    if st.button("Start another comparison", type="primary"):
        reset_evaluation()
