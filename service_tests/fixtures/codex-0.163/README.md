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
and `AgentMessage` items, alongside response-item copies. In this 4.44.2 source,
they exercise the existing file-mirror connectors in both `messages` and
`complete` modes: first prefix and resume, an independent thread, stable repeat
revisions and current reader access. The
[public compatibility validation](../../../docs/validation/2026-10-21-codex-compatibility.md)
records the source checks and their limits. Durable L1 retained-inbox capture
belongs to separate development work and is not included in this patch. The
producer provenance above is shared evidence; it does not transfer that branch's
capture or installed-acceptance results to this one.
