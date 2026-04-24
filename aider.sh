#!/usr/bin/env bash
set -euo pipefail

echo "Starting Aider through LiteLLM..."
docker compose --profile aider run --rm aider --model claude-sonnet "$@"
