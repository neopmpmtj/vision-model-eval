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
