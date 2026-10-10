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
