# Vision Model Eval

Django app for comparing OpenAI vision models on one image with optional system instructions and an optional user prompt. Supports blind human ratings and automated latency benchmarks, with full per-turn metadata stored in SQLite.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Set your OpenAI key in `.env` at the **project root**:

```
OPENAI_API_KEY=sk-...
```

Django reads the root `.env`, not `scripts/openai-image-evaluator/.env`.

## Run

```bash
python manage.py migrate
python manage.py runserver
```

Open http://127.0.0.1:8000/ — the **console** lists all runs with cross-run stats. Start a new session at http://127.0.0.1:8000/new/

To start with an empty database (drops all runs):

```bash
rm db.sqlite3
python manage.py migrate
```

## URLs

| Path | Purpose |
|------|---------|
| `/` | Console hub — run list, filters, cross-run stats |
| `/new/` | New session (upload image, choose models) |
| `/run/<uuid>/` | Blind evaluate (generate + rate) |
| `/run/<uuid>/benchmark/` | Latency benchmark (auto-run all models) |
| `/run/<uuid>/results/` | Completed-session results |
| `/run/<uuid>/inspect/` | Full run inspector (any status) |
| `/run/<uuid>/turn/<index>/` | Turn detail (JSON, latencies, tokens) |
| `/run/<uuid>/download/` | CSV export (partial runs included) |
| `/admin/` | Django admin (requires superuser) |

## Session types

Choose a session type on the new-session page (`/new/`):

| Type | Purpose |
|------|---------|
| **Blind comparison** | Upload an image, generate one anonymous response per model, rate each 1–5, then reveal model names |
| **Latency benchmark** | Run models one at a time with no ratings; read each response and latency before continuing |

Blind mode randomizes model order. Benchmark mode runs models in the order selected.

On `/new/`:

| Control | Sent to the API |
|---------|-----------------|
| **System instructions** preset (describe, OCR, inventory, uncertainty) | Responses `instructions` (system/developer). Additional text is appended when present. |
| **Omit system instructions** | No `instructions` kwarg. Additional text is required and sent as user `input_text`. |
| **Additional instructions** | Appended to the preset, or (when omit is on) the only user text. |
| **Session description** | Not sent. Stored on the run for console/inspect/CSV. |

Default: describe preset as `instructions`, user content is the image only.

## Data model

```
EvaluationRun          image, instructions, user_prompt, optional description, model list, image metadata, API defaults
    ├── EvaluationTurn     one row per model API call (latencies, tokens, request/response JSON)
    └── LatencyBenchmark   optional OneToOne FK; session aggregates for benchmark runs only
```

`EvaluationRun.instructions` is the Responses API system/developer message (empty when omitted). `EvaluationRun.user_prompt` is user `input_text` (empty when the user message is the image only). `EvaluationRun.description` is optional human metadata — not sent to the API.

Compose happens in `image_evaluator.prompt_presets.compose_eval_text` — views do not concatenate strings.

There is no `prompt` column. `LatencyBenchmark.notes` exists but is unused (kept). `EvaluationTurn.time_to_first_token_seconds` is reserved for streaming and is always null.

Run type is inferred from related records — there is no `mode` column on `EvaluationRun`. A benchmark run has a linked `LatencyBenchmark` row; a blind comparison does not.

### Per-turn metadata (`EvaluationTurn`)

Recorded immediately when a model responds (or fails), including:

- Wall and OpenAI-reported latency, request start/finish timestamps
- Token counts: input, output, total, reasoning, cached, cache-write
- API request snapshot: `instructions`, `user_prompt`, reasoning, `max_output_tokens`, `store`, image detail
- API response snapshot: response id, status, model, timestamps
- Full `usage_raw` JSON
- Optional rating, notes, `rated_at` (blind mode only)
- Reserved: `time_to_first_token_seconds` (for future streaming)

Partial and abandoned runs are kept in the database.

### Benchmark aggregates (`LatencyBenchmark`)

- Expected turn count, success/failure counts
- Total and average wall latency
- Status and timestamps

## CSV export

Runs with at least one turn can be downloaded as CSV from the results or inspect page. Exports include turn-level fields, `instructions`, `user_prompt`, `session_description`, and `benchmark_id` when the run was a latency benchmark.

## API key validation

The prepare page validates the key once per session (free `models.list()` check). Use `?recheck=1` to force a re-check.

**Unit tests** (mocked, no network):

```bash
python manage.py test image_evaluator.tests
python manage.py test image_evaluator.tests --exclude-tag=openai
```

**Live OpenAI tests** (key check + small billable vision probe):

```bash
python manage.py test image_evaluator.tests.test_api_key --tag=openai
```

## Configuration

Optional defaults in `config/settings.py` (pre-filled on `/new/`, snapshotted per run):

| Setting | Default |
|---------|---------|
| `MODEL_LABS` | OpenAI enabled; Gemini/DeepSeek stubs |
| `EVAL_PROMPT_PRESETS` | describe, ocr, inventory, uncertainty (`EVAL_PROMPT_DEFAULT_ID` = `describe`) |
| `DEFAULT_EVAL_PROMPT` | Same text as the `describe` preset |
| `OPENAI_DEFAULT_REASONING_EFFORT` | `low` (SDK: none, minimal, low, medium, high, xhigh, max) |
| `OPENAI_DEFAULT_REASONING_MODE` | `standard` (SDK: standard, pro) |
| `OPENAI_DEFAULT_MAX_OUTPUT_TOKENS` | `1600` |
| `OPENAI_DEFAULT_IMAGE_DETAIL` | `auto` (SDK: auto, low, high, original) |
| `OPENAI_DEFAULT_STORE` | `False` |

Chosen values (including `lab`, `omit_instructions`, `prompt_preset`) are stored in `EvaluationRun.api_defaults`. Per-turn `api_request` records what was actually sent (`instructions` omitted from the API call when empty).

## Project layout

| Path | Description |
|------|-------------|
| `config/` | Django settings and URLs |
| `image_evaluator/` | App: models, views, services, templates |
| `image_evaluator/services/` | OpenAI client, API key validation, turn persistence |
| `.env` | Secrets (not committed) |
| `db.sqlite3` | SQLite database |
| `media/uploads/` | Uploaded images |
| `scripts/openai-image-evaluator/` | Original Streamlit prototype |

## Admin

Register runs, turns, and benchmarks at http://127.0.0.1:8000/admin/ after creating a superuser:

```bash
python manage.py createsuperuser
```
