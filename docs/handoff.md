# Session handoff

Last updated: 2026-08-30 10:25 (UTC+1)

## Project

**Vision Model Eval** — Django app to compare OpenAI vision models on one image + one prompt. SQLite database. No auth.

## Read first

1. This file
2. [`README.md`](../README.md)
3. [`AGENTS.md`](../AGENTS.md) — agent do/don't

No `docs/PROJECT-PLAN.md` yet.

## Done (as of 2026-08-30)

- Django project: `config/`, `image_evaluator/`, root `.env` via `python-decouple`
- **Blind comparison**: randomized model order, generate → rate → reveal → CSV
- **Latency benchmark**: `LatencyBenchmark` table (OneToOne → `EvaluationRun`), auto-sequential run, no ratings
- **EvaluationTurn**: full metadata per API call (latencies, tokens, `api_request`/`api_response`/`usage_raw`); persisted on generate, including errors
- **EvaluationRun**: status, image dimensions/size, `api_defaults` snapshot
- API key validation on prepare page; tests in `test_api_key.py` (unit + `@tag('openai')` live probe)
- Migrations through `0002_comprehensive_metadata` (data migrated from `EvaluationRating`)
- `.cursor/` folder scaffold
- `AGENTS.md` at repo root
- **Console dashboard** at `/` — run list, filters, cross-run stats, per-model summaries
- **Inspect pages** at `/run/<id>/inspect/` and `/run/<id>/turn/<n>/` — full metadata without Django admin
- Prepare form moved to `/new/`; site nav on all pages
- **Pickable API defaults** on `/new/` (reasoning effort/mode, tokens, image detail, store) using official OpenAI SDK enums; snapshotted in `api_defaults`
- **MODEL_LABS** catalog (OpenAI enabled; Gemini/DeepSeek stubs); lab select on prepare form
- **Benchmark UX**: one model per request on `/run/<id>/benchmark/`; first model auto-runs; user reads full response + latency then continues via `?continue=1`
- **Latency metrics documented**: Wall (s) = precise `perf_counter()` around `client.responses.create()`; OpenAI (s) = rough `completed_at − created_at` (often whole-second timestamps, can be higher or lower than wall). Labels + footnote on results table; docstring on `_openai_latency_seconds()`; tests in `test_metadata.py`
- **Prompt presets** on `/new/` (`EVAL_PROMPT_PRESETS` in settings): dropdown fills the prompt textarea; edited text wins on POST; `custom` preset when user edits
- **Session description** optional on `/new/` → `EvaluationRun.description` (metadata only, not sent to OpenAI); shown on console/inspect/sidebars; CSV column `session_description`
- Migration `0003_evaluationrun_description`

## Not done

- Streaming / TTFB measurement
- User authentication
- Production deploy (PostgreSQL, static files, etc.)
- Formal phased project plan
- Prompt library (save/reuse named prompts) and vector search on session descriptions

## Locked decisions

- Root `.env` is the only Django secrets file (not `scripts/.../.env`)
- No `mode` on `EvaluationRun` — benchmark vs blind inferred from `LatencyBenchmark` presence
- Turns saved immediately; ratings optional on `EvaluationTurn`
- Benchmark runs one model per step on `/run/<id>/benchmark/`; user reads each response then continues
- `/` is the console hub; `/new/` is the prepare form (URL name `prepare` unchanged)
- **Wall (s)** is the authoritative latency for benchmarks; **OpenAI (s)** is a coarse server-side estimate only (~1s resolution)

## Next (suggested)

- Run real eval/benchmark sessions and use the console to compare across runs
- Add `.cursor/rules/` for Django/OpenAI conventions if patterns stabilize
- Add `docs/PROJECT-PLAN.md` when scope grows beyond eval + latency tooling

## Commands

```bash
source .venv/bin/activate
python manage.py migrate
python manage.py runserver
.venv/bin/python manage.py test image_evaluator.tests --exclude-tag=openai
```

## Session log

### 2026-08-30 10:25 (UTC+1)

- Prompt preset dropdown on `/new/` (describe, OCR, inventory, uncertainty, custom); textarea text snapshotted to `EvaluationRun.prompt`
- Optional session description on runs; console column + CSV `session_description`; not sent to API
- Tests in `test_prompt_presets.py`

### 2026-08-30 10:06 (UTC+1)

- Clarified Wall vs OpenAI latency: wall is precise client wait; OpenAI is rough `completed_at − created_at` (integer-second timestamps common)
- Benchmark page shows full response text per model; interactive step-through (`?continue=1`) instead of all models in one request
- Results table: client/server column labels + help footnote
- Tests in `MetadataExtractionTests` document OpenAI latency can exceed or be less than wall

### 2026-08-30 09:35 (UTC+1)

- Pickable API options on `/new/` with official SDK enums; run snapshot drives generate/benchmark
- MODEL_LABS catalog; AGENTS.md rule for doc-backed enums and error turns
- Tests in `test_api_defaults.py`

### 2026-08-30 09:15 (UTC+1)

- Added console dashboard (`/`), inspect run/turn pages, site nav
- Moved prepare form to `/new/`; CSV export works for partial runs
- Tests in `test_console.py`; updated README and handoff

### 2026-08-30 09:03 (UTC+1)

- Created comprehensive metadata model (`EvaluationTurn`, `LatencyBenchmark`)
- Updated README, `.cursor/` structure, `AGENTS.md`, this handoff
