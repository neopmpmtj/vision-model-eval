# Session handoff

Last updated: 2026-08-30 09:03 (UTC+1)

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

## Not done

- Streaming / TTFB measurement
- User authentication
- Analytics across runs
- Production deploy (PostgreSQL, static files, etc.)
- Formal phased project plan

## Locked decisions

- Root `.env` is the only Django secrets file (not `scripts/.../.env`)
- No `mode` on `EvaluationRun` — benchmark vs blind inferred from `LatencyBenchmark` presence
- Turns saved immediately; ratings optional on `EvaluationTurn`
- Benchmark runs all models in one request cycle on `/run/<id>/benchmark/`

## Next (suggested)

- Run real eval/benchmark sessions and inspect data via admin or CSV
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

### 2026-08-30 09:03 (UTC+1)

- Created comprehensive metadata model (`EvaluationTurn`, `LatencyBenchmark`)
- Updated README, `.cursor/` structure, `AGENTS.md`, this handoff
