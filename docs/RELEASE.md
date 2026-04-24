# Release Readiness

## Version discipline

- Current repo version lives in `VERSION`
- Human-facing changes go to `CHANGELOG.md`
- Generated artifacts are part of the operational contract

## Post-update checklist

1. Update `VERSION` if the release boundary changed
2. Update `CHANGELOG.md`
3. Run `.\stack.ps1 refresh` or `./stack.sh refresh`
4. Review `SELF_CHECK.txt`
5. Open `dashboards/index.html`
6. Run `.\stack.ps1 backup` if a recoverable milestone snapshot is needed

## Self-check regeneration logic

`refresh` is the supported regeneration pipeline:

- `doctor`
- `status`
- `smoke`
- `validate`
- dashboard render
- `SELF_CHECK.txt` rewrite

This keeps the operational story reproducible instead of manually edited.
