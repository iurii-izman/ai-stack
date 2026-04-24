# Future Extensibility

The repo now has an explicit slot for future modules in `ops/extensions.catalog.json`.

## Why this exists

Future growth should not happen by smuggling extra services into README, dashboard, or compose without ownership. Every new module must define:

- runtime boundary
- profile or host ownership
- storage ownership
- backup and restore story
- operator commands
- dashboard visibility rules

## Planned module categories

- `search`
- `vector-db`
- `observability`
- `code-tools`
- `browser-tools`

These are not shipped services yet. They are planning slots only.

## Rule for adding a new module

1. Add it to `ops/extensions.catalog.json`
2. Extend `ops/stack.manifest.json` if it becomes supported
3. Wire it into `ops/ai_stack.py`
4. Regenerate artifacts with `stack refresh`
5. Update architecture and release docs
