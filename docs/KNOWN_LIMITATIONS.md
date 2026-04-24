# Known Limitations

- Ollama is still host-managed and not started or stopped by Compose.
- The dashboard is a generated HTML snapshot. It does not stream live telemetry.
- `coding` is an ergonomic module, not a persistent daemon.
- Open WebUI can take longer during the first warm start because it initializes assets and migrations.
- Cloud aliases stay declared even when their provider key is absent. This is intentional and surfaced by `doctor`.
