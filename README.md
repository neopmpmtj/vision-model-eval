# Vision Model Eval

Django app for blind comparison of OpenAI vision models on a single image and prompt.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` at the **project root** and set your OpenAI key:

```
OPENAI_API_KEY=sk-...
```

Django reads the root `.env`, not `scripts/openai-image-evaluator/.env`.

## Run

```bash
python manage.py migrate
python manage.py runserver
```

Open http://127.0.0.1:8000/

## API key health check

Unit tests (mocked, no network):

```bash
python manage.py test image_evaluator.tests.test_api_key
```

Live OpenAI validation (free key check + small billable vision probe):

```bash
python manage.py test image_evaluator.tests.test_api_key --tag=openai
```

The prepare page also validates the key once per session (free `models.list()` check).

## Layout

- `config/` — Django settings and project URLs
- `image_evaluator/` — evaluation app (models, views, OpenAI service, templates)
- `.env` — secrets (not committed)
- `db.sqlite3` — SQLite database

The original Streamlit prototype remains under `scripts/openai-image-evaluator/`.
