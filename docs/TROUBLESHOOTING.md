# Troubleshooting Matrix

| Symptom | Likely cause | Check | Fix |
| --- | --- | --- | --- |
| `doctor` fails on Docker daemon | Docker Desktop is not running | `docker info` | Start Docker Desktop |
| `smoke` fails on LiteLLM | `core` is down or `LITELLM_KEY` mismatch | `.\stack.ps1 status`, `.\stack.ps1 logs litellm` | Start `core`, verify `.env` |
| `smoke` warns on Ollama | Host Ollama is not running | `Invoke-WebRequest http://localhost:11434/api/tags` | Start Ollama or ignore if local model fallback is not needed |
| `ui` is idle | `warm` profile not started | `.\stack.ps1 status` | Run `.\stack.ps1 start ui` |
| `validate` reports broken links | Docs mention files that do not exist anymore | `.\stack.ps1 validate` | Fix the referenced doc paths or remove stale references |
| `backup` fails on Postgres dump | Postgres container unavailable | `docker compose ps` | Start `core` or rerun backup |
| Dashboard looks stale | Artifacts were not regenerated | Check timestamps in `dashboards/index.html` and `SELF_CHECK.txt` | Run `.\stack.ps1 refresh` |

## Known verification shortcuts

- `doctor` is for prerequisites and conflicts
- `smoke` is for live endpoint reachability
- `validate` is for repository consistency
- `refresh` is the release-style end-to-end check
