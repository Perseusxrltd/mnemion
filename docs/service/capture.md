# Conversation capture

Capture is opt-in. Select an export/session folder through a filesystem, Git,
Drive or rclone connection, map its intended audience, and set
`normalize_conversations: true` on that provider. Run `mnemion-connect --watch`
to reconcile the selected source periodically. Mnemion does not search personal
assistant histories or install hooks on its own.

The ordinary raw file is retained as source evidence. Readable companion notes
carry the raw document hash, external identity, conversation ID, normalizer
version and turn count. They are observed notes, not verified company facts.
The raw file remains the complete record, including tool data or alternative
branches omitted from the readable conversation.

| Export | Readable companion |
| --- | --- |
| Codex JSONL | Canonical user/agent event messages, without duplicate response items |
| Grok Build / ACP `session/update` JSONL (4.16.0+) | User/agent text chunks grouped by session and message; tool, thought and status updates stay in raw evidence |
| Claude Code JSONL | Human/assistant text turns; tool payloads remain in the raw record |
| ChatGPT JSON or `conversations.json` | Active `current_node` branch, including multiple conversations |
| Claude privacy export | Conversation IDs, sender identities and text blocks |
| Slack JSON export | Actual user/bot identities and thread groups; never invented assistant roles |
| Generic `role`/`content` array | Recorded roles and text |
| Unknown valid JSON | Raw evidence only |

An old ChatGPT tree with multiple leaves and no active node remains raw rather
than guessing its final branch. Normalization does not correct spelling or call
a model. A partially written JSONL file aborts the inventory, so its absence
cannot certify deletion. The next completed scan retries it.

For ACP logs, adjacent chunks for the same speaker/message are joined verbatim,
without inserting spaces or newlines. Explicit message IDs and tool/turn boundaries
separate messages. Interleaved session IDs remain separate companions. The label
shows the first/last chunk timestamps when they differ; the raw record retains
every event timestamp. Identical repeated events deduplicate only when the source
provides an explicit `eventId`; conflicting reuse is reported. Repeated text
without an event identity is preserved, since it can be intentional. Repeated
source imports and appends retain the same companion identity and raw-source
provenance. This supports the native shape reported in
[issue 40](https://github.com/Perseusxrltd/mnemion/issues/40); it does not install a
Grok plugin or automatically select a user's private session directory.

**Live-file limitation:** the existing file adapters require a complete, stable
file within their configured size cap. A partial, oversized or changing file
can suspend that source scope until a complete scan succeeds. Use stable,
deliberately split exports or curated notes for now. The dedicated bounded,
checkpointed live-conversation adapter is tracked in
[issue 41](https://github.com/Perseusxrltd/mnemion/issues/41), including tail
completion, append/rename/rotation/truncation, source offsets and removal/access
semantics. Conversation normalization does not change these limits or relax
the complete-inventory requirement for Git memory journals.

Readable notes use the same revision, conflict and deletion rules as other
connector records. Human corrections and quarantine produce review proposals
when the source changes. Deleting a particular imported part/companion prevents
that identity from being recreated by a later scan. Removing an entire upstream
document is reconciled across its imported parts only after a complete scan.
Disabling or pausing the connection immediately closes its shared access.

Raw and readable notes retain independent review state. A correction to one
does not claim to correct the other. Use source review and explicit revisions
for organizational decisions; imported assistant statements are not automatically
trusted. Changing normalization options changes the selected inventory. Enable
the option before the initial import when possible.

## Optional session hook

For an assistant supporting a stop/session hook, register the following command
using that assistant's documented hook configuration:

```sh
mnemion-capture-hook --config /path/to/connector.json
```

Use the absolute installed executable path when the GUI does not inherit your
terminal environment. Hook installation is explicit and separate from MCP setup.
The hook requests one bounded scan of the already configured source, ignoring
paths, credentials and commands in the incoming event. It returns `{}` so a
deferred capture does not block the conversation. The default deadline is 20
seconds; use a watch process for larger imports. Source files are the durable
retry input, not an in-memory queue.

The historical `hooks/mnemion_save_hook.py` routes to this workflow when
`MNEMION_CONNECTOR_CONFIG` is set. Without it, the optional private-profile
extractor remains available. Git union sync is retired. The shared connector
coordinates retries across machines through service checkpoints and leases.
