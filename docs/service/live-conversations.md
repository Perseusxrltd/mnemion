# Live conversation sources

Mnemion 4.17.0 adds the opt-in `conversations` adapter for growing JSONL logs.
It captures the prefix of **complete, LF-terminated records** in each selected
file. An unfinished last record waits for another scan, including an incomplete
UTF-8 character. A valid final JSON value without its newline also waits: a
writer may still append to it.

Each file becomes a separate managed source space with its own access lease.
A malformed or oversized record closes that file's source until it can be
captured again; other files continue. Ordinary notes belong in a filesystem or
Git connection. Existing file adapters still require complete stable files.
Git memory journals must use the [journal connector](git-journal.md), including
its complete catalog and denials. This adapter rejects journal records.

## Set up in the app

1. Upgrade the server and source runner to **4.17.0 or later**.
2. In **Sources**, register **Live agent conversations** with a dedicated
   application. Map the intended people and agents to source identities.
3. Download the configuration and select the session folder on its host. Keep
   the checkpoint directory private to that OS account. Each capture host needs
   its own connection and checkpoint directory.
4. Inspect the selected sources, then run the watcher on that host:

```sh
mnemion-connect --config connector.json --inspect
mnemion-connect --config connector.json --watch
```

The app shows each file's captured and pending bytes, source bytes read, and
fragments reused or processed at its last complete scan. Source pause/resume,
audience mappings and **Sync now** use the existing controls. Configuring and
launching the source host remains an operator step; registering a connection
does not grant the app remote access to arbitrary local folders.

```json
{
  "version": 1,
  "service_url": "https://memory.example.com",
  "connector_id": "00000000-0000-0000-0000-000000000001",
  "service_token": {"env": "MNEMION_CONNECTOR_KEY"},
  "provider": {
    "type": "conversations",
    "path": "./selected-sessions",
    "state_directory": "./.mnemion-conversations",
    "scope_id": "engineering-agent-host",
    "name": "Engineering agent sessions",
    "members": ["employee:alice", "agent:research"],
    "publish_to_mapped_members": true,
    "include": ["*.jsonl"],
    "normalize_conversations": true,
    "max_file_bytes": 1000000000,
    "max_record_bytes": 2000000,
    "segment_bytes": 256000,
    "segment_records": 256,
    "max_scan_seconds": 120
  },
  "poll_seconds": 300
}
```

Replace the example connector ID and URL. Relative paths resolve beside the
configuration on Windows, macOS and Linux. The default credential/settings
exclusions remain in force; only selected `.jsonl` files enter this adapter.
Publication uses the explicitly mapped audience, rather than translating OS or
cloud ACLs into company membership. The runner must still be able to open the
source through a verified handle before and after capture. Source content never
chooses a file path, runs a command or grants access.

## Checkpoints, source evidence and bandwidth

Fragments end at complete record boundaries. The last fragment can grow until
its byte/record target is reached; earlier fragments stay stable. Raw evidence
retains exact record text, segment hashes and byte/line offsets. Large fragments
use the existing 48,000-character API parts: `document_start`/`document_end`
are character offsets within that fragment; `source_byte_start`/`source_byte_end`
identify its containing range in the original file. Keep the source files for
byte-level archival and full file recovery.

Readable companions use the [supported conversation formats](capture.md).
Codex session headers retain their original identity and header hash across
fragments. Explicit ACP event identities deduplicate across fragments and scans;
conflicting reuse fails visibly. Raw duplicate events remain in the evidence.
A streamed turn spanning fragments is shown as fragments, with
`conversation_turn_fragments` metadata, rather than a claimed full-session
turn count. Tool/thought/status data stays in raw evidence. Set
`normalize_conversations: false` for raw records only.

The private SQLite checkpoint contains identities, offsets, hashes and event
IDs, not conversation bodies or credentials. It uses a 2 MiB database cache and
an OS account lock. Checkpoints commit only after the service acknowledges a
complete inventory. A missing, stale or unacknowledged checkpoint causes a full
evidence replay; it does not certify that local work was uploaded.

An unchanged file requires no content reads. When a file grows, the runner
**rehashes the sealed prefix** before reusing it, then parses the final fragment
and new records. This detects earlier edits combined with an append. Prefix
verification still costs disk I/O; it avoids repeatedly parsing, transmitting
and embedding the whole conversation. Read counters measure bytes returned by
file reads, including validation and data served by the OS cache. They do not
measure physical disk or network traffic.

Reused fragments send `action: "retain"` with exact source ID and revision.
The service accepts only a revision already present in that source scope.
References cannot create evidence, change a correction, replace a proposal or
revive a deleted identity. Every scan still provides a complete inventory of
the captured record prefix before pruning. A final page stores bounded progress
counters; only successful finish commits them to the source checkpoint.
HTTP, Python and MCP agents can read those counters through the existing
connector scope operations. The TypeScript `conversationCapture()` helper
validates them for display.

## Changes and access

- Appending during a scan does not extend the read indefinitely. The runner
  verifies the captured prefix, reports later bytes as pending and reads them
  on a subsequent scan. Changing already-read bytes fails that attempt.
- Replacing a file or truncating captured history starts a new source generation.
  This keeps new events from inheriting old deleted fragment positions. Rewriting
  only an unfinished tail preserves the captured generation. Rewrites within an
  existing generation reprocess the affected evidence and retain normal review
  conflict handling.
- Renaming or deleting a file closes the old file's scope after a complete
  directory catalog. A renamed file has its own path identity. Closed scope
  evidence may remain stored under the workspace's retention rules; scope
  suspension is access withdrawal, not a promise of physical erasure.
- Forgetting a fragment prevents that generation's identity from being replayed.
  New generations, renamed copies and external archives are separate observations;
  deleting an imported memory cannot erase the source archive. Organization
  policy and current mappings continue to govern every generation.
- Removing a mapping, disabling the connection, pausing a source or losing
  access denies affected readers. Cached fragments cannot restore a removed
  mapping. An unreadable/incomplete directory catalog cannot certify missing
  files; known scopes are suspended conservatively until access is rechecked.

## Bounded work and remaining limits

| Setting | Default | Supported range |
| --- | --- | --- |
| Selected files | 1,000 | 1–100,000 |
| File bytes per scan | 1 GB | 1 B–1 TB |
| Bytes in one complete or pending record | 2 MB | 1 B–16 MB |
| Target fragment bytes | 256 kB | 1,024 B–1 MB |
| Target records per fragment | 256 | 1–10,000 |
| Fragments per file | 100,000 | 1–1,000,000 |
| Time per file scan | 120 seconds | 1–600 seconds |

A record may exceed the fragment target up to the record limit. Work exceeding
a configured bound fails visibly for that file; no source tail is silently
discarded. The checkpoint database is also bounded to 1 GiB. Limits are safety
bounds, not measured throughput promises: very large inputs need a suitable host,
scan budget and deliberately bounded producer output. Lower record/fragment
limits reduce peak rendering memory.

Native assistant plugin installation, provider event feeds, a fully guided
source-host launcher, scan scheduling across large fleets and a producer-backed
append protocol that can avoid full prefix verification remain on the roadmap.
This adapter neither selects personal histories automatically nor turns an
incomplete file into a complete Git journal or a full backup.
