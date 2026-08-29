#!/usr/bin/env bash

set -Eeuo pipefail

APP_NAME="OpenAI Image Evaluator"
DEFAULT_PROJECT_DIR="${PWD}/openai-image-evaluator"

info() {
    printf '\n[%s] %s\n' "$APP_NAME" "$1"
}

fail() {
    printf '\n[%s] ERROR: %s\n' "$APP_NAME" "$1" >&2
    exit 1
}

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

install_python_packages() {
    if ! command_exists apt-get; then
        fail "This installer supports Ubuntu/Debian systems that use apt-get."
    fi

    info "Python or its virtual-environment support is missing. Installing it now."
    sudo apt-get update
    sudo apt-get install -y python3 python3-venv python3-pip
}

printf '\n%s\n' "=== $APP_NAME installer ==="
printf '%s\n' "This creates a local Streamlit app for blind comparison of OpenAI vision models."

read -r -p "Installation folder [${DEFAULT_PROJECT_DIR}]: " PROJECT_DIR_INPUT
PROJECT_DIR="${PROJECT_DIR_INPUT:-$DEFAULT_PROJECT_DIR}"

if [[ "$PROJECT_DIR" != /* ]]; then
    PROJECT_DIR="${PWD}/${PROJECT_DIR}"
fi

if [[ "$PROJECT_DIR" == "/" ]]; then
    fail "The filesystem root cannot be used as the project directory."
fi

if [[ -e "$PROJECT_DIR" ]] && [[ -n "$(find "$PROJECT_DIR" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]; then
    fail "The target folder already exists and is not empty: $PROJECT_DIR"
fi

if ! command_exists python3; then
    install_python_packages
fi

if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
    fail "Python 3.10 or newer is required."
fi

mkdir -p "$PROJECT_DIR"

info "Creating the Python virtual environment."
if ! python3 -m venv "$PROJECT_DIR/.venv"; then
    install_python_packages
    python3 -m venv --clear "$PROJECT_DIR/.venv"
fi

cat > "$PROJECT_DIR/requirements.txt" <<'REQUIREMENTS'
openai>=2.0,<3
streamlit>=1.49,<2
python-dotenv>=1.0,<2
pandas>=2.0,<3
REQUIREMENTS

cat > "$PROJECT_DIR/.gitignore" <<'GITIGNORE'
.env
.venv/
__pycache__/
*.py[cod]
results.csv
GITIGNORE

cat > "$PROJECT_DIR/app.py" <<'PYTHON'
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
PYTHON

cat > "$PROJECT_DIR/set_api_key.sh" <<'KEYSCRIPT'
#!/usr/bin/env bash
set -Eeuo pipefail

KEY_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
read -r -s -p "Paste your OpenAI API key (input is hidden): " OPENAI_KEY_INPUT
printf '\n'

if [[ -z "$OPENAI_KEY_INPUT" ]]; then
    printf '%s\n' "No key was entered. Nothing changed." >&2
    exit 1
fi

if [[ "$OPENAI_KEY_INPUT" == *$'\n'* || "$OPENAI_KEY_INPUT" == *$'\r'* ]]; then
    printf '%s\n' "The key contains an invalid newline." >&2
    exit 1
fi

umask 077
printf 'OPENAI_API_KEY=%s\n' "$OPENAI_KEY_INPUT" > "$KEY_SCRIPT_DIR/.env"
chmod 600 "$KEY_SCRIPT_DIR/.env"
unset OPENAI_KEY_INPUT
printf '%s\n' "API key saved to the private .env file."
KEYSCRIPT

cat > "$PROJECT_DIR/run.sh" <<'RUNSCRIPT'
#!/usr/bin/env bash
set -Eeuo pipefail

RUN_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$RUN_SCRIPT_DIR"

if [[ ! -x ".venv/bin/python" ]]; then
    printf '%s\n' "Virtual environment not found. Run the setup installer again." >&2
    exit 1
fi

exec .venv/bin/streamlit run app.py
RUNSCRIPT

cat > "$PROJECT_DIR/README.md" <<'README'
# OpenAI Image Understanding Evaluator

A local Streamlit application for comparing several OpenAI vision-capable models with one fixed image and one fixed prompt.

## Run

```bash
./run.sh
```

Streamlit will print a local address, normally `http://localhost:8501`.

## Change the API key

```bash
./set_api_key.sh
```

The key is saved in `.env`, protected with owner-only file permissions and excluded from Git.

## Evaluation flow

1. Upload one image.
2. Enter the prompt that every model must receive.
3. Select at least two OpenAI models.
4. Generate and rate each anonymous response.
5. Reveal the models and download the comparison table after rating them all.

All completed ratings are also appended to `results.csv` in the project folder.

## Stop the app

Return to the terminal and press `Ctrl+C`.
README

chmod 700 "$PROJECT_DIR/set_api_key.sh"
chmod 755 "$PROJECT_DIR/run.sh"

info "Installing Python dependencies."
"$PROJECT_DIR/.venv/bin/python" -m pip install --upgrade pip
"$PROJECT_DIR/.venv/bin/python" -m pip install -r "$PROJECT_DIR/requirements.txt"

info "Saving your OpenAI API key. The characters you type will not be displayed."
"$PROJECT_DIR/set_api_key.sh"

printf '\n%s\n' "Setup complete."
printf '%s\n' "Project folder: $PROJECT_DIR"
printf '%s\n' "Future start command: $PROJECT_DIR/run.sh"

read -r -p "Launch the application now? [Y/n]: " LAUNCH_REPLY
if [[ ! "$LAUNCH_REPLY" =~ ^[Nn]$ ]]; then
    exec "$PROJECT_DIR/run.sh"
fi

