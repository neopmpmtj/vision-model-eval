# Session handoff

Last updated: 2026-08-30 14:50 (UTC+1)

## Project

**Vision Model Eval** — Django app to compare OpenAI vision models on one image plus optional system instructions and user prompt. SQLite database. No auth.

## Read first

1. This file
2. [`README.md`](../README.md)
3. [`AGENTS.md`](../AGENTS.md) — agent do/don't

No `docs/PROJECT-PLAN.md` yet.

## Done (as of 2026-08-30)

- Django project: `config/`, `image_evaluator/`, root `.env` via `python-decouple`
- **Blind comparison**: randomized model order, generate → rate → reveal → CSV
- **Latency benchmark**: `LatencyBenchmark` OneToOne → `EvaluationRun`; one model per request; user continues via `?continue=1`
- **EvaluationTurn**: latencies, tokens, `api_request` / `api_response` / `usage_raw`; success and error turns persisted on generate
- **EvaluationRun**: `instructions`, `user_prompt`, `description`, image metadata, `api_defaults`, status. No `prompt` column. No `mode` column
- Migrations through **`0004_run_instructions_user_prompt`**
- API key validation on `/new/`; tests in `test_api_key.py` (unit + `@tag('openai')` live probe)
- Console `/`, inspect run/turn, site nav, CSV (includes `instructions`, `user_prompt`, `session_description`)
- Pickable API defaults (SDK enums) + `MODEL_LABS` (OpenAI on; Gemini/DeepSeek stubs)
- **System instructions** presets (`EVAL_PROMPT_PRESETS`); **Omit system instructions** → user-only `input_text`; `compose_eval_text()` is the compose helper
- Wall (s) = `perf_counter()` around `responses.create`; OpenAI (s) = coarse `completed_at − created_at`
- Busy overlay spinner on generate, benchmark continue, prepare submit, and API-key recheck

## Not done

- Streaming / TTFB (`time_to_first_token_seconds` always null — reserved)
- User authentication
- Production deploy (PostgreSQL, static files, etc.)
- Formal phased project plan
- Prompt library (save/reuse) and vector search on `description`
- Per-turn cost estimate (token counts exist; no USD on the Responses object)

## Locked decisions

- Root `.env` is the only Django secrets file
- No `mode` on `EvaluationRun` — benchmark vs blind from `LatencyBenchmark` presence
- Turns saved immediately; ratings optional on `EvaluationTurn`
- Benchmark: one model per step on `/run/<id>/benchmark/`
- `/` = console; `/new/` = prepare (`prepare` URL name)
- **Wall (s)** is the latency for benchmarks; **OpenAI (s)** is a coarse estimate
- Presets are Responses **`instructions`**, not a Custom textarea. Additional appends when presets are on; omit sends additional as `user_prompt` only
- `description` is metadata only — never sent to OpenAI
- Keep `LatencyBenchmark.notes` (unused) and TTFB column; do not drop them unless asked
- Safe to delete `db.sqlite3` and `migrate` for a data-empty start; schema still comes from migrations

## Next (suggested)

- Delete `db.sqlite3` if you want a clean local DB, then `python manage.py migrate`
- Run real eval/benchmark sessions
- Add `.cursor/rules/` if conventions stabilize
- Add `docs/PROJECT-PLAN.md` only when scope grows

## Commands

```bash
source .venv/bin/activate
python manage.py migrate
python manage.py runserver
.venv/bin/python manage.py test image_evaluator.tests --exclude-tag=openai
```

## Session log

### 2026-08-30 14:50 (UTC+1)

- Shared `#busy-overlay` spinner in `base.html`; `data-wait` on generate/rate, benchmark continue, prepare, and API-key recheck

### 2026-08-30 11:00 (UTC+1)

- Docs pass: README prepare-flow table; AGENTS compose/instructions rules; schema notes (no `prompt` column; TTFB reserved; `LatencyBenchmark.notes` unused but kept)
- Resetting local SQLite (`rm db.sqlite3` + migrate) is the intended empty-data start

### 2026-08-30 10:55 (UTC+1)

- Greenfield prompt split: `instructions` vs `user_prompt`
- Omit checkbox; additional appends to preset or is the only user prompt
- Removed Custom preset
- Tests in `test_prompt_presets.py`

### 2026-08-30 10:25 (UTC+1)

- Prompt presets + session description (later superseded by instructions split)
- CSV `session_description`

### 2026-08-30 10:06 (UTC+1)

- Wall vs OpenAI latency; benchmark step-through; results footnote

### 2026-08-30 09:35 (UTC+1)

- Pickable API options; MODEL_LABS; `test_api_defaults.py`

### 2026-08-30 09:15 (UTC+1)

- Console, inspect pages, prepare at `/new/`

### 2026-08-30 09:03 (UTC+1)

- `EvaluationTurn` / `LatencyBenchmark` model
