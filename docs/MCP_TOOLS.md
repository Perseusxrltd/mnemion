# Mnemion MCP Tools

Mnemion MCP exposes read, write, trust, graph, diary, and maintenance tools. Mutating tools write a redacted WAL entry to `~/.mnemion/wal/write_log.jsonl`.

## Drawer Operations

- `mnemion_get_drawer(drawer_id)`
- `mnemion_list_drawers(wing?, room?, limit?, offset?)`
- `mnemion_add_drawer(wing, room, content, source_file?)`
- `mnemion_update_drawer(drawer_id, content?, wing?, room?)`
- `mnemion_delete_drawer(drawer_id)`

Content updates create a superseding drawer and mark the old trust record `superseded`. Metadata-only moves update Chroma, FTS, and trust location in place.

## Explicit Tunnels

- `mnemion_create_tunnel(source_wing, source_room, target_wing, target_room, label?, source_drawer_id?, target_drawer_id?)`
- `mnemion_list_tunnels(wing?)`
- `mnemion_delete_tunnel(tunnel_id)`
- `mnemion_follow_tunnels(wing, room)`

Tunnels are stored under the Mnemion config directory as `tunnels.json`.

## Maintenance

- `mnemion_reconnect()`
- `mnemion_hook_settings(silent_save?, desktop_toast?)`
- `mnemion_memories_filed_away()`
- `mnemion_repair_status()`
- `mnemion_status()`

If the HNSW health probe detects divergence, vector loading is disabled. `mnemion_status` and `mnemion_repair_status` still respond, search uses lexical fallback where possible, and duplicate detection reports a limitation instead of returning false negatives.
