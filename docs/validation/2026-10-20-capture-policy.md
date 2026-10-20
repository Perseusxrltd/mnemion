# Selected live capture — 20 October 2026

Source 4.41 adds complete-record and message-only capture choices using the
existing source inventory, current permission and checkpoint contracts.

**53 parser/stream/HTTP/PostgreSQL cases passed**, including the new choice for
Codex, Claude Code, ACP/Grok and generic role/content streams. Message-only
capture preserves the selected UTF-8 message text and provenance while omitting
structured tool/reasoning/private instruction fixtures from both source content
and metadata. Unchanged checkpoints retain existing projections without reading
the file again. Changing modes re-examines prior references; disabling message
normalization in message-only mode is rejected.

A real HTTP/PostgreSQL transition started with complete raw and readable records,
then completed a message-only inventory. Only the selected message projection
remained current and readable; the next unchanged scan created no revision.
Existing cases cover incomplete/oversized records, changed prefixes, missing
acknowledgments, cross-fragment event identity, current authorization, corrections,
quarantine and retained deletions. This does not certify erasure from historical
backups or the original source files.

The native source configuration case passed with explicit mode propagation and
rejection on other provider types. All **17 TypeScript client cases** and **eight
desktop source-controller cases** passed; source mode survives protected storage
and reopening. The SDK, Electron and desktop frontend builds passed. No external
model, provider account or production source was used.

**The actual Electron app journey also passed** against an isolated PostgreSQL
workspace and operating-system credential store. The app selected message-only
capture, enrolled a disposable source and completed its scan; native agent
inspection reported the same mode. The resulting memory contained the selected
message and excluded the structured tool fixture. The 500-pixel view had no
horizontal overflow and was visually inspected. There were no browser console
errors, model calls or changes to personal source configuration.

Initial harness attempts lacked the engine wrapper or a working isolated
credential store; the existing app correctly held source creation when secure
storage was unavailable. A later harness assertion queried the wrong database
column after the app flow had succeeded. These fixture failures were retained,
corrected and rerun; the complete app/database case passed in 30.55 seconds.

Full native publication remains subject to the automated
[release status](../RELEASE_STATUS.md) and
[maintenance board](../MAINTENANCE_STATUS.md).
