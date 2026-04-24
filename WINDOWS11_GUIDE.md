# Windows 11 Guide

## Supported paths

### Recommended

- Docker Desktop on Windows
- Python 3.11+ inside WSL2
- Ollama on the Windows host if local model fallback is needed
- Commands executed through `install.sh` and `stack.sh`

### Supported

- Docker Desktop on Windows
- Python 3.11+ on Windows
- Optional Ollama on the host
- Commands executed through `stack.ps1`

## PowerShell happy path

```powershell
cd C:\Dev\ai-stack
.\install-windows.ps1
.\stack.ps1 start core
.\stack.ps1 doctor
.\stack.ps1 smoke
```

For UI:

```powershell
.\stack.ps1 start ui
```

For Aider:

```powershell
.\aider.bat
```

## Main operator commands

```powershell
.\stack.ps1 start core
.\stack.ps1 start ui
.\stack.ps1 status
.\stack.ps1 logs litellm
.\stack.ps1 validate
.\stack.ps1 backup
.\stack.ps1 refresh
```

## What `refresh` does

- runs `doctor`
- runs `status`
- runs `smoke`
- runs `validate`
- rewrites `dashboards/index.html`
- rewrites `SELF_CHECK.txt`

## Limitations

- Dashboard is a local HTML snapshot, not a PWA.
- Ollama is not managed by Compose.
- The `ui` module maps to compose profile `warm`.
