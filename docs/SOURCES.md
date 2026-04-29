# Source Adapter Plugins

Mnemion source adapters let new origins feed drawers into an Anaktoron without coupling every importer to the miner internals.

Entry point group:

```toml
[project.entry-points."mnemion.sources"]
my_adapter = "my_package:MyAdapter"
```

Core types live in `mnemion.sources`:

- `SourceRef`
- `RouteHint`
- `SourceItemMetadata`
- `DrawerRecord`
- `SourceSummary`
- `FieldSpec`
- `AdapterSchema`
- `BaseSourceAdapter`
- `AnaktoronContext`

Adapter construction must be lightweight: no network calls, no source scans, and no credential fetch. Secrets must not be placed in `SourceRef.options`; adapters should name required environment variables when raising `AuthRequiredError`.

`DrawerRecord.metadata` must contain only flat scalars compatible with ChromaDB: `str`, `int`, `float`, `bool`, or `None`.

Candidate adapters:

- filesystem/project
- Claude Code JSONL
- Codex CLI JSONL
- Gemini CLI JSONL
- Slack export
- GitHub
- Cursor
- OpenClaw/Hermes custom logs
