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
