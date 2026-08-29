# Vision Model Eval

Django app for blind comparison of OpenAI vision models on a single image and prompt.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Put your OpenAI key in `.env` at the project root:

```
OPENAI_API_KEY=sk-...
```

## Run

```bash
python manage.py migrate
python manage.py runserver
```

Open http://127.0.0.1:8000/

## Layout

- `config/` — Django settings and project URLs
- `image_evaluator/` — evaluation app (models, views, OpenAI service, templates)
- `.env` — secrets (not committed)
- `db.sqlite3` — SQLite database

The original Streamlit prototype remains under `scripts/openai-image-evaluator/`.
