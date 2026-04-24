#!/usr/bin/env bash
set -euo pipefail

random_hex() {
  openssl rand -hex "${1:-24}"
}

echo "Preparing AI Stack workspace..."

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required. Install Docker Desktop and enable WSL integration before running this script." >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "docker compose is required. Install the Docker Compose v2 plugin." >&2
  exit 1
fi

if ! command -v openssl >/dev/null 2>&1; then
  echo "openssl is required to generate local secrets." >&2
  exit 1
fi

if grep -qi microsoft /proc/version 2>/dev/null; then
  echo "WSL detected."
else
  echo "Running on Linux. The supported Windows flow uses WSL2 or PowerShell on the host."
fi

if command -v ollama >/dev/null 2>&1; then
  echo "Ollama detected."
else
  echo "Ollama not found. Install it separately if you want the optional local model fallback."
fi

mkdir -p backups config data

if [ ! -f .env ]; then
  litellm_key="sk-$(random_hex 16)"
  webui_secret="$(random_hex 32)"
  postgres_password="$(random_hex 24)"

  cat > .env <<EOF
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GOOGLE_API_KEY=
OPENROUTER_API_KEY=
LITELLM_KEY=${litellm_key}
WEBUI_SECRET_KEY=${webui_secret}
POSTGRES_USER=postgres
POSTGRES_DB=postgres
POSTGRES_PASSWORD=${postgres_password}
DATABASE_HOST=postgres
DATABASE_PORT=5432
DATABASE_NAME=postgres
DATABASE_USER=postgres
DATABASE_USERNAME=postgres
DATABASE_PASSWORD=${postgres_password}
DATABASE_SCHEMA=public
DATABASE_URL=postgresql://postgres:${postgres_password}@postgres:5432/postgres
WEBUI_ADMIN_EMAIL=
WEBUI_ADMIN_PASSWORD=
WEBUI_ADMIN_NAME=Admin
EOF
  echo "Created .env with generated local secrets."
else
  echo ".env already exists; leaving it unchanged."
fi

cat <<'EOF'

Next steps:
1. Add any cloud API keys you want to use to .env.
2. Start the core stack: ./stack.sh start core
3. Start Open WebUI when needed: ./stack.sh start ui
4. Run doctor: ./stack.sh doctor
5. Run smoke checks: ./stack.sh smoke

Optional local Ollama model:
  ollama pull qwen2.5-coder:1.5b
EOF
