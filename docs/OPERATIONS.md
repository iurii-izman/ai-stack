# Operations

## Operator entrypoints

- PowerShell: `.\stack.ps1`
- WSL2 / shell: `./stack.sh`

## Daily commands

| Goal | PowerShell | Shell |
| --- | --- | --- |
| Start core | `.\stack.ps1 start core` | `./stack.sh start core` |
| Start UI | `.\stack.ps1 start ui` | `./stack.sh start ui` |
| Stop everything | `.\stack.ps1 stop` | `./stack.sh stop` |
| Restart UI | `.\stack.ps1 restart ui` | `./stack.sh restart ui` |
| Doctor | `.\stack.ps1 doctor` | `./stack.sh doctor` |
| Status | `.\stack.ps1 status` | `./stack.sh status` |
| Logs | `.\stack.ps1 logs litellm` | `./stack.sh logs litellm` |
| Smoke | `.\stack.ps1 smoke` | `./stack.sh smoke` |
| Validate | `.\stack.ps1 validate` | `./stack.sh validate` |
| Backup | `.\stack.ps1 backup` | `./stack.sh backup` |
| Refresh artifacts | `.\stack.ps1 refresh` | `./stack.sh refresh` |

## Command semantics

- `doctor`: environment and drift diagnostics
- `status`: current runtime snapshot
- `smoke`: endpoint-level runtime checks
- `validate`: docs/files/compose/env consistency checks
- `refresh`: runs doctor + status + smoke + validate and regenerates `SELF_CHECK.txt` plus `dashboards/index.html`

## Logs and service inspection

Examples:

```powershell
.\stack.ps1 logs postgres
.\stack.ps1 logs litellm
.\stack.ps1 status --json
```

```bash
./stack.sh logs postgres
./stack.sh logs litellm
./stack.sh status --json
```

## Backup and recovery

Create a snapshot:

```powershell
.\stack.ps1 backup
```

```bash
./stack.sh backup
```

What the snapshot contains:

- `.env`
- compose and config files
- `postgres.dump`
- `open-webui-data.tgz`
- `metadata.json`

Restore from a snapshot:

```powershell
.\stack.ps1 restore .\backups\YYYYMMDD-HHMMSS
```

```bash
./stack.sh restore ./backups/YYYYMMDD-HHMMSS
```

Optional:

- add `--restore-env` if the backed-up `.env` should overwrite the current one

## Artifact regeneration

After meaningful config or doc changes:

```powershell
.\stack.ps1 refresh
```

This is the supported way to keep the dashboard and self-check aligned with the repo.
