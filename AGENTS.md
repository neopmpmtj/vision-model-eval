# Vision Model Eval — Agent instructions

Django 5.2 + SQLite app for **blind comparison** and **latency benchmarking** of frontier vision models (OpenAI, Google Gemini, DeepSeek) on a single image with optional system instructions and user prompt. Per-turn metadata (latencies, tokens, API request/response JSON) is persisted in SQLite. No user authentication.

**▶ Read [`docs/handoff.md`](docs/handoff.md) first** — condensed state, locked decisions, and the suggested next task. Then [`README.md`](README.md) for setup, data model, and tests.

There is **no `docs/PROJECT-PLAN.md` yet** — do not invent phased roadmaps; update `docs/handoff.md` at the end of substantive sessions.

## Session handoff (August 2026)

**Done:**

- Django project at repo root: `config/` + `image_evaluator/` app
- Blind comparison flow (upload → generate per model → rate → results + CSV)
- Latency benchmark mode (auto-sequential, no ratings, `LatencyBenchmark` aggregates)
- Turn-based persistence: `EvaluationRun` → `EvaluationTurn` (replaces `EvaluationRating`)
- Partial and abandoned runs kept in DB (`RunStatus.abandoned`)
- Full per-turn metadata: wall/OpenAI latency, token breakdown, `api_request` / `api_response` / `usage_raw` JSON
- Multi-lab eval: OpenAI, Google Gemini (2.5 + 3.x), DeepSeek vision — parallel `*_eval.py` modules + `eval_dispatch`
- Per-lab API keys (`OPENAI_API_KEY`, `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`) validated on prepare POST and evaluate/benchmark
- `python-decouple` for `.env` at **project root** (not `scripts/openai-image-evaluator/.env`)
- `.cursor/` scaffold (rules, skills, agents, commands, hooks)
- Unit tests: `test_api_key`, `test_metadata`, `test_console`, `test_api_defaults`, `test_prompt_presets`, `test_multi_lab`
- Console dashboard at `/`, inspect pages, site nav; prepare at `/new/`
- System-instruction presets + omit checkbox; `EvaluationRun.instructions` / `user_prompt` / `description`

**Not done / deferred:**

- Streaming / TTFB (`time_to_first_token_seconds` column exists, always null)
- User authentication
- Background jobs for benchmark runs (stepped in-browser flow is intentional)
- Production deployment hardening (PostgreSQL, `DEBUG=False`, etc.)
- Formal project plan document
- Prompt library (save/reuse named prompts) and vector search on session descriptions

**Next (suggested):** use the app for real eval runs; add `docs/PROJECT-PLAN.md` only when scope grows. Consider project-specific `.cursor/rules/` for Django/OpenAI conventions.

## Current state (what exists)

### Apps

| App | Purpose |
|-----|---------|
| `image_evaluator` | Models, views, templates, multi-lab services, tests |
| `config` | Settings (`python-decouple`), URLs, WSGI/ASGI |

### Data model

```text
EvaluationRun     image, instructions, user_prompt, description, model_order, api_defaults, image metadata, status
    ├── EvaluationTurn       one row per API call (metadata + optional rating)
    └── LatencyBenchmark     OneToOne FK; benchmark sessions only (no mode enum on Run)
```

Run type: benchmark if `run.latency_benchmark` exists; otherwise blind comparison.

### Services (`image_evaluator/services/`)

| Module | Role |
|--------|------|
| `openai_eval.py` | OpenAI Responses `analyze_image`, `ApiRequestConfig` |
| `gemini_eval.py` | Gemini `generate_content`, `GeminiApiRequestConfig` |
| `deepseek_eval.py` | DeepSeek Responses `analyze_image`, `DeepSeekApiRequestConfig` |
| `eval_dispatch.py` | Routes `analyze_image` / `build_api_request_dict` by `lab` |
| `analysis.py` | Shared `AnalysisResult` DTO |
| `lab_api_key.py` | Per-lab `validate_lab_api_key()`, billable probes |
| `api_key.py` | Shared status types; OpenAI re-exports |
| `turns.py` | `save_success_turn()`, `save_error_turn()` |
| `prompt_presets.py` (app root) | `compose_eval_text()`, preset catalog helpers |

### URLs

| Path | View |
|------|------|
| `/` | Console (run list + stats) |
| `/new/` | Prepare (session type + upload) |
| `/run/<uuid>/` | Blind evaluate (generate + rate) |
| `/run/<uuid>/benchmark/` | Auto-run all models |
| `/run/<uuid>/results/` | Results table + CSV download |
| `/run/<uuid>/inspect/` | Full run inspector (any status) |
| `/run/<uuid>/turn/<index>/` | Turn detail (JSON + metadata) |

### Prototype (do not extend unless asked)

`scripts/openai-image-evaluator/` — original Streamlit app; separate `.env`. Django uses root `.env` only.

## Architecture conventions

```text
views.py  →  services/  →  models.py  →  SQLite
```

- **Business logic in `image_evaluator/services/`**, not in views or templates
- **Persist turns on generate** (success or error); ratings attach to existing `EvaluationTurn` rows in blind mode
- **Do not add a `mode` field on `EvaluationRun`** — use `LatencyBenchmark` FK to distinguish benchmark sessions
- **One lab per session** — `api_defaults["lab"]` selects provider; do not mix labs in one run
- **Parallel provider modules** — no shared Provider ABC; add labs via catalog + `*_eval.py` + dispatch branch
- **Snapshot API defaults** into `EvaluationRun.api_defaults` at session creation (`lab`, `omit_instructions`, `prompt_preset`, plus lab-specific params); per-turn `api_request` records what was sent
- **Eval text:** `compose_eval_text()` → `run.instructions` + `run.user_prompt`. Pass Responses `instructions` only when non-empty; user `input_text` only when `user_prompt` is non-empty. Do not restore a `prompt` column.
- **API parameter enums** (reasoning effort/mode, image detail, etc.) must match official OpenAI docs / installed SDK types — do not guess
- Plain Django templates + minimal inline CSS — no React/Vue
- **Minimize scope** — focused diffs; match existing patterns in `views.py`, `models.py`, services

## Do

- Read `docs/handoff.md` and `README.md` before large changes
- Use `.venv/bin/python` for `manage.py` and tests (or activate the venv first)
- Run `python manage.py test image_evaluator.tests --exclude-tag=openai` after code changes
- Put secrets in root `.env` only; use `.env.example` as the committed template
- Keep latency/metadata fields on `EvaluationTurn`; aggregates on `LatencyBenchmark`
- Record failed API calls as `EvaluationTurn` with `status=error`
- When adding form choices or API parameter enums, read the **current** official provider docs and installed SDK types (e.g. `.venv/.../openai/types/...`). Do not invent or truncate lists from memory
- If the provider rejects a parameter value (model-dependent support), persist `EvaluationTurn` with `status=error`, `error_type`, and `error_message`; surface it in the UI. Do not silently remap to another value
- Update `docs/handoff.md` at the end of a session with what changed and what is next

## Do not

- Commit `.env`, API keys, `db.sqlite3`, or `media/uploads/`
- Copy OpenAI keys from `scripts/openai-image-evaluator/.env` into tracked files
- Store turn data only in the session — DB is the source of truth
- Conflate ratings with turn records (ratings are nullable fields on `EvaluationTurn`)
- Run live OpenAI tests (`--tag=openai`) in CI without explicit intent — they cost tokens
- Guess API enum members, copy stale Chat Completions lists when the app uses Responses, or catch API errors without writing an error turn
- Edit the plan files in `.cursor/plans/` unless the user asks
- Over-engineer: no extra abstractions, queues, or auth unless requested

## Commands

```bash
source .venv/bin/activate
cp .env.example .env          # OPENAI_API_KEY, GEMINI_API_KEY, DEEPSEEK_API_KEY
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver      # http://127.0.0.1:8000/
```

**Tests:**

```bash
.venv/bin/python manage.py test image_evaluator.tests --exclude-tag=openai
.venv/bin/python manage.py test image_evaluator.tests.test_api_key --tag=openai   # live API; costs tokens
```

**Admin:**

```bash
python manage.py createsuperuser
```

## Security

- Do not commit `.env` or real API keys
- Do not log or print `OPENAI_API_KEY`, `GEMINI_API_KEY`, or `DEEPSEEK_API_KEY`
- Uploaded images live under `media/` (gitignored)

## Configuration

Loaded via `python-decouple` from root `.env`. Defaults in `config/settings.py`:

- `MODEL_LABS` — lab-grouped model catalog (`openai`, `google`, `deepseek` enabled)
- `OPENAI_API_KEY`, `GEMINI_API_KEY`, `DEEPSEEK_API_KEY` — root `.env` only
- `AVAILABLE_MODELS` — derived from enabled labs (do not pass to OpenAI `models.list()`)
- `EVAL_PROMPT_PRESETS` / `EVAL_PROMPT_DEFAULT_ID` / `DEFAULT_EVAL_PROMPT` — system-instruction catalog
- OpenAI / Gemini / DeepSeek default API params in `config/settings.py` (snapshotted per run)

## Cursor project config

| Path | Use |
|------|-----|
| [`.cursor/rules/`](.cursor/rules/) | Project rules (`.mdc`) |
| [`.cursor/skills/`](.cursor/skills/) | Project skills |
| [`.cursor/agents/`](.cursor/agents/) | Custom subagents |
| [`.cursor/commands/`](.cursor/commands/) | Slash commands |
| [`.cursor/hooks/`](.cursor/hooks/) | Hook scripts + `hooks.json` |

## Documentation conventions

- **No PROJECT-PLAN yet** — track state in `docs/handoff.md` and `README.md`
- When adding review or audit docs under `docs/`, use dated filenames: `topic-YYYY-MM-DD-HHMM.md`
- End of session: update [`docs/handoff.md`](docs/handoff.md) (done / not done / next)

## Before large changes

1. [`docs/handoff.md`](docs/handoff.md)
2. [`README.md`](README.md)
3. [`image_evaluator/models.py`](image_evaluator/models.py) and [`image_evaluator/services/`](image_evaluator/services/)
4. Existing tests in [`image_evaluator/tests/`](image_evaluator/tests/)
