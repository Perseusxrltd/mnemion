# Codex 0.163.0 producer fixtures

An actual `codex-cli 0.163.0` native binary produced these JSONL files on
21 October 2026. A deterministic local Responses provider supplied synthetic
replies for three CLI turns; Codex generated the records, timestamps and thread
identities. All three invocations exited successfully. The original
`producer.receipt.json` passed at 16:48 UTC; the earlier failed mount attempt
remains preserved with the private producer evidence.

| File | Provenance |
| --- | --- |
| [resumed.jsonl](resumed.jsonl) | Two turns in the same thread, including an actual CLI resume. The manifest pins the byte length and hash of the first-turn prefix before resume. |
| [independent.jsonl](independent.jsonl) | One turn in a distinct thread created by a separate CLI invocation. |
| [manifest.json](manifest.json) | Native producer hash, complete file hashes and lengths, thread identities, and the synthetic prompts and replies. |

The copied file bytes match the original producer receipt. Preserve these bytes,
including line endings, metadata and identifiers; do not normalize or redact the
records. The repository's [.gitattributes](../../../.gitattributes) disables line
ending conversion for these JSONL files.

The normal Codex profile was hidden. The producer used a separate network
namespace with no outbound routes, made no paid model calls and wrote no
production memories. No real user sources or credentials were supplied.
`HOME` remained unchanged: the original metadata retains the synthetic working
directory `/fixture/project` and the HOME-derived system-skills path emitted by
the CLI. Those metadata bytes have not been rewritten.

The provider setup followed the official [Codex configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)
for a custom `base_url` and `wire_api = "responses"`, and the official
[Responses streaming guide](https://developers.openai.com/api/docs/guides/streaming-responses)
for typed response events. The fetched sources and their hashes are retained in
`official-config-reference.source.json` and
`official-response-streaming.source.json` with the private producer evidence.

These fixtures contain `event_msg` / `item_completed` records with `UserMessage`
and `AgentMessage` items, alongside response-item copies. Source parser and
actual-corpus HTTP/PostgreSQL checks passed for both `messages` and `complete`
modes, including resume, restart and forgetting boundaries. Follow the
[current implementation checkpoint](../../../docs/research/2026-10-21-durable-capture-implementation.md#current-codex-producer-21-october-2026)
for the scoped results and retained failures. Full native acceptance at the
current exact source, shared-host operation and device recovery remain open.

The same exact producer corpus also qualifies the separate public 4.44.2
[mirror-connector correction](../../../docs/validation/2026-10-21-codex-compatibility.md).
That focused patch excludes unfinished L1; its 66-case source result remains
separate from this development branch's durable-inbox and native acceptance.
