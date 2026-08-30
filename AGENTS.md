# Vision Model Eval — Agent instructions

Django 5.2 + SQLite app for **blind comparison** and **latency benchmarking** of OpenAI vision models on a single image and prompt. Per-turn metadata (latencies, tokens, API request/response JSON) is persisted in SQLite. No user authentication.

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
- API key validation on prepare page (free `models.list()`); live tests include billable vision probe (`@tag('openai')`)
- `python-decouple` for `.env` at **project root** (not `scripts/openai-image-evaluator/.env`)
- `.cursor/` scaffold (rules, skills, agents, commands, hooks)
- Unit tests: `image_evaluator.tests.test_api_key`, `image_evaluator.tests.test_metadata`, `image_evaluator.tests.test_console`
- Console dashboard at `/`, inspect pages, site nav; prepare at `/new/`

**Not done / deferred:**

- Streaming / TTFB (`time_to_first_token_seconds` column exists, always null)
- User authentication
- Background jobs for benchmark runs (sequential in-request is intentional)
- Production deployment hardening (PostgreSQL, `DEBUG=False`, etc.)
- Formal project plan document

**Next (suggested):** use the app for real eval runs; add `docs/PROJECT-PLAN.md` only when scope grows. Consider project-specific `.cursor/rules/` for Django/OpenAI conventions.

## Current state (what exists)

### Apps

| App | Purpose |
|-----|---------|
| `image_evaluator` | Models, views, templates, OpenAI services, tests |
| `config` | Settings (`python-decouple`), URLs, WSGI/ASGI |

### Data model

```text
EvaluationRun     image, prompt, model_order, api_defaults, image metadata, status
    ├── EvaluationTurn       one row per API call (metadata + optional rating)
    └── LatencyBenchmark     OneToOne FK; benchmark sessions only (no mode enum on Run)
```

Run type: benchmark if `run.latency_benchmark` exists; otherwise blind comparison.

### Services (`image_evaluator/services/`)

| Module | Role |
|--------|------|
| `openai_eval.py` | `analyze_image()`, `ApiRequestConfig`, `AnalysisResult` |
| `api_key.py` | `validate_api_key()`, `run_billable_probe()` |
| `turns.py` | `save_success_turn()`, `save_error_turn()`, benchmark completion |

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
- **Snapshot API defaults** into `EvaluationRun.api_defaults` at session creation; per-turn `api_request` records what was sent
- Plain Django templates + minimal inline CSS — no React/Vue
- **Minimize scope** — focused diffs; match existing patterns in `views.py`, `models.py`, services

## Do

- Read `docs/handoff.md` and `README.md` before large changes
- Use `.venv/bin/python` for `manage.py` and tests (or activate the venv first)
- Run `python manage.py test image_evaluator.tests --exclude-tag=openai` after code changes
- Put secrets in root `.env` only; use `.env.example` as the committed template
- Keep latency/metadata fields on `EvaluationTurn`; aggregates on `LatencyBenchmark`
- Record failed API calls as `EvaluationTurn` with `status=error`
- Update `docs/handoff.md` at the end of a session with what changed and what is next

## Do not

- Commit `.env`, API keys, `db.sqlite3`, or `media/uploads/`
- Copy OpenAI keys from `scripts/openai-image-evaluator/.env` into tracked files
- Store turn data only in the session — DB is the source of truth
- Conflate ratings with turn records (ratings are nullable fields on `EvaluationTurn`)
- Run live OpenAI tests (`--tag=openai`) in CI without explicit intent — they cost tokens
- Edit the plan files in `.cursor/plans/` unless the user asks
- Over-engineer: no extra abstractions, queues, or auth unless requested

## Commands

```bash
source .venv/bin/activate
cp .env.example .env          # set OPENAI_API_KEY
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
- Do not log or print `OPENAI_API_KEY`
- Uploaded images live under `media/` (gitignored)

## Configuration

Loaded via `python-decouple` from root `.env`. Defaults in `config/settings.py`:

- `OPENAI_DEFAULT_REASONING_EFFORT`, `OPENAI_DEFAULT_MAX_OUTPUT_TOKENS`, `OPENAI_DEFAULT_IMAGE_DETAIL`, `OPENAI_DEFAULT_STORE`
- `AVAILABLE_MODELS` — checkbox choices on prepare form

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
