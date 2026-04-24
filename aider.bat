@echo off
setlocal

echo Starting Aider through LiteLLM...
docker compose --profile aider run --rm aider --model claude-sonnet %*
