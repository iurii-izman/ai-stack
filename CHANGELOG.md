# Changelog

## Unreleased

### Added

- Truth-driven operations CLI in `ops/ai_stack.py` with PowerShell and shell wrappers.
- Architecture manifest, generated dashboard flow, backup and restore scaffolding, and consistency validation.

### Changed

- Docs reorganized into quick start plus deep-dive operational guides.
- Legacy helper scripts now delegate to the unified operator CLI.

### Verification

- Run `./stack.sh refresh` or `.\stack.ps1 refresh`
- Review `SELF_CHECK.txt`
- Open `dashboards/index.html`
