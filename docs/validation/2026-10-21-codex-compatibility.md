# Codex 0.163 conversation compatibility validation

Recorded **21 October 2026** during 4.44.2 source preparation, based on the
4.44.1 revision-2 source `92d5e505`. This patch adds the current Codex parser,
cache and readable-revision correction to the existing public mirror connectors.
It contains no durable L1 retained-capture implementation and leaves all
[65 product requirements](../PRODUCT_REQUIREMENTS.md) and L1–L7 in scope.

## Producer and source correction

The [fixture provenance](../../service_tests/fixtures/codex-0.163/README.md)
records an actual Codex CLI 0.163.0 run: three synthetic turns across two JSONL
files, including resume of the first thread. The native producer and copied
bytes are pinned by the manifest. A deterministic local Responses provider,
hidden normal profile and isolated network kept the producer independent of
paid models, real user sources and account credentials.

The [parser](../../mnemion/conversations.py) now reads public text from
`event_msg` / `item_completed` records carrying `UserMessage` or `AgentMessage`.
It omits malformed/non-text blocks and duplicate response-item copies, preserves
repeated spoken messages, and retains support for older Codex message events.
The `mnemion-conversation-v1` projection format stays compatible. A separate
renderer revision makes live scans revisit previously omitted prefixes;
readable companions include their text hash so changed output receives a new
revision without changing the source or conversation identity.

## Recorded source evidence

The public baseline retained **8 failures** in `public-parser-baseline.log`.
The corrected parser, legacy-format, ACP, live-file and real mirror
HTTP/PostgreSQL group passed **66 cases in 35.34 seconds**, recorded in
`public-parser-corrected.log`. These results belong to this public compatibility
patch; no test totals from the separate durable-capture development branch are
carried over.

The [parser regressions](../../tests/test_codex_conversations.py) cover the actual
corpus, malformed item types, private/non-text blocks, repeated messages,
re-examination of an omitted prefix and changed readable output with an unchanged
raw revision.

The [mirror HTTP/PostgreSQL journeys](../../service_tests/test_codex_live_compatibility.py)
exercise both `complete` and `messages` modes. They ingest the actual first-turn
prefix, append the producer's real resumed suffix, and ingest the independent
thread. Each of the six spoken messages is readable exactly once. Messages mode
excludes raw/context records; repeated scans preserve memory revisions, and a
reader removed from the source binding is denied access.

These are source and mirror-connector results. At this recorded checkpoint,
the exact candidate's installed-platform, release and public-update gates were
still pending. Durable offline inbox acceptance, shared-host/device recovery
and full L1 completion remain separate work.

See the [release notes](../releases/4.44.2.md) for behavior and the
[live release status on main](https://github.com/Perseusxrltd/mnemion/blob/main/docs/RELEASE_STATUS.md)
or [published releases](https://github.com/Perseusxrltd/mnemion/releases) for
current availability. The recorded source evidence above remains a dated
checkpoint when this document is bundled offline or viewed in a release tag.
