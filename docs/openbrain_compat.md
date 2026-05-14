# Open Brain-Compatible MCP Aliases

Mnemion exposes simple MCP tool names for interoperability with clients that expect a universal memory backend. This is a clean-room compatibility layer: it does not copy OB1 code, docs, or storage design.

## Tools

- `capture_thought`
- `search_thoughts`
- `list_thoughts`
- `thought_stats`
- `search`
- `fetch`

All tools route into normal Mnemion storage, search, trust, source, and wiki systems. They do not create a second database.

## Examples

Minimal MCP smoke sequence:

1. Call `capture_thought`:

```json
{
  "content": "Hybrid retrieval should remain the default retrieval path.",
  "tags": ["mnemion"],
  "privacy_class": "private"
}
```

2. Call `search`:

```json
{
  "query": "hybrid retrieval"
}
```

3. Pass any returned typed ID to `fetch`:

```json
{
  "id": "drawer:drawer_thoughts_mnemion_..."
}
```

`search` returns typed IDs:

```text
drawer:<drawer_id>
source:<source_id>
chunk:<chunk_id>
wiki:<page_path>
```

Pass those IDs to `fetch` for grounded content.

## Trust And Privacy

Search results preserve trust status and contested warnings. Quarantined source, chunk, drawer, and wiki evidence is excluded or refused by default. Superseded drawers stay governed by Mnemion's native trust filtering.

## Remote Exposure Warning

These aliases expose real local Mnemion memory through MCP. Keep stdio/local MCP
as the default transport. Do not expose the tools over HTTP or a remote bridge
without a separate token, audit, and network policy review; mutating tools such
as `capture_thought` write into the normal Mnemion store.
