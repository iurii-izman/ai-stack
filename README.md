# AI Stack

Локальный AI stack для Windows 11 / WSL2 с правдивой архитектурой, единым operator CLI и генерируемыми operational artifacts.

## Quick start

### Security note

Do not commit your `.env` file to GitHub or any public repository. Use `.env.sample` for example values and store real secrets in secure storage (Windows Credential Manager, environment variables, or a secret manager). The installer will generate local secrets for testing, but you must rotate cloud API keys before publishing.

### WSL2 / Linux shell

```bash
chmod +x install.sh stack.sh
./install.sh
./stack.sh start core
./stack.sh doctor
./stack.sh smoke
```

### PowerShell

```powershell
.\install-windows.ps1
.\stack.ps1 start core
.\stack.ps1 doctor
.\stack.ps1 smoke
```

Для UI:

```bash
./stack.sh start ui
```

```powershell
.\stack.ps1 start ui
```

## What is actually supported

- Compose profiles: `hot`, `warm`, `aider`
- Logical operator modules: `core`, `ui`, `coding`
- Real services:
  - `postgres`
  - `litellm`
  - `open-webui`
  - `aider` as on-demand helper
  - `ollama` as host dependency
- Generated operational artifacts:
  - `dashboards/index.html`
  - `SELF_CHECK.txt`

## Operator commands

```bash
./stack.sh start core
./stack.sh stop
./stack.sh restart ui
./stack.sh doctor
./stack.sh status
./stack.sh logs litellm
./stack.sh smoke
./stack.sh validate
./stack.sh backup
./stack.sh refresh
```

PowerShell:

```powershell
.\stack.ps1 start core
.\stack.ps1 stop
.\stack.ps1 restart ui
.\stack.ps1 doctor
.\stack.ps1 status
.\stack.ps1 logs litellm
.\stack.ps1 smoke
.\stack.ps1 validate
.\stack.ps1 backup
.\stack.ps1 refresh
```

## Modules and profiles

- `core` maps to compose profile `hot`: `postgres` + `litellm`
- `ui` maps to `warm`: adds `open-webui`
- `coding` maps to `aider`: on-demand helper on top of the core module

Это модульный слой для оператора. Compose остаётся простым и честным, без лишнего размножения профилей.

## Runtime model routing

LiteLLM aliases in `litellm-config.yaml`:

- `openai-gpt4`
- `claude-sonnet`
- `claude-4-opus`
- `gemini-pro`
- `mistral-openrouter`
- `ollama-coder-local`

Если cloud key отсутствует, соответствующий alias остаётся сконфигурированным, но нерабочим. Это диагностирует `doctor`.

## Source of truth

- Architecture truth layer: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Operations handbook: [docs/OPERATIONS.md](docs/OPERATIONS.md)
- Troubleshooting matrix: [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)
- Known limitations: [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md)
- Future module slots: [docs/EXTENSIBILITY.md](docs/EXTENSIBILITY.md)
- Release discipline: [docs/RELEASE.md](docs/RELEASE.md)

## Dashboard and self-check

- Dashboard: [dashboards/index.html](dashboards/index.html)
- Self-check report: [SELF_CHECK.txt](SELF_CHECK.txt)

Оба артефакта генерируются командой:

```bash
./stack.sh refresh
```

или:

```powershell
.\stack.ps1 refresh
```
