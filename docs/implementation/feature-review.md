# Feature review and product decisions

Mnemion is shared memory infrastructure for people, teams and applications using
multiple assistants, systems and devices. Its organizing principle is a stable,
permission-aware record of evidence and decisions. Obsidian remains a portable
visualization and personal annotation surface.

## Required for the current release

| Capability | Product decision |
| --- | --- |
| Many sources, one memory contract | Ship provider adapters plus an open connector protocol. Git, Drive, Slack, selected folders and rclone are the first included adapters. Avoid a promise that every provider/account/file format is already certified. |
| Company permissions | Keep source access boundaries through retrieval, citations, history, context and exports. Require explicit identity mappings; expire stale access. Never translate “the bot can read this” into “the whole team can read this.” |
| Cross-device coordination | Keep canonical state and checkpoints on the service. Use per-application credentials, idempotency, optimistic versions and leases so multiple hardware instances can retry safely. |
| Human knowledge and source changes | Preserve corrections and quarantine; expose incoming conflicts. Keep source text separate from verified claims. Deletions and revoked access take precedence over old projections and backups. |
| Migration without feature loss | Complete the [v3 parity audit](v3-feature-parity.md), including capture, agent setup and source/wiki workflows. Keep experiments optional and valuable private-profile behavior recoverable. |
| Open data and visualization | Retain Markdown, YAML, links, stable IDs, exact source evidence, typed APIs, SDKs and MCP. Protect manual Obsidian sections and validate native platforms. |
| Operations and public release | Supply a reproducible deployment, observable readiness/failures, recovery rehearsal, security/dependency review, native validation, documented limits and a clean public repository. |
| Memory bandwidth and machine limits | Bound inference concurrency, queue admission, batches, input size, database work and diagnostics. Support lightweight clients using a remote service. Report actual model/process resource use and document deployment sizing. |
| Embedding choice and safe upgrades | Provide a current, licensed model catalog with small CPU, stronger local and hosted choices. Fingerprint model/tokenizer/pooling/dimensions and preserve existing generations. Reindex and verify before activation; retain a rollback path. No single model is best for every language, machine and corpus. |
| Configurable librarian | Allow a selected small local or remote model to organize, identify duplicates/conflicts/staleness and propose evidence-backed changes. Apply current permissions, source checks, structured proposals, review policies, scheduling and cost/resource limits. A model's agreement is not proof of a claim. |
| Visual observability and evaluation | Ship a detailed, interactive workspace for memory/source health, indexing throughput, retrieval, model/resource use and reproducible evaluations. Include drill-down, dataset/version management, run controls, comparisons, exports, uncertainty and documented metric definitions. Keep diagnostics bounded and distinguish estimates and unavailable measurements. |

## Options worth adding with explicit boundaries

| Option | Value | Boundary / release treatment |
| --- | --- | --- |
| Conversation-aware capture | Retains decisions across coding agents and chat exports | Adapt existing normalizers and hooks; require selected paths, source identity and provenance. Do not silently scan every user's history. |
| Project/user/task context profiles | Gives each agent the appropriate compact context | Use scoped core blocks, metadata and token budgets. Derived profiles must identify evidence and expire when evidence changes. |
| Evidence-linked wiki and graph | Makes a company memory understandable and navigable | Preserve manual additions; invalidate stale generated content. Confident prose is not a substitute for supported citations. |
| Additional synthesis / reflection strategies | Can extend the required configurable librarian with specialized maintenance policies | Keep model use opt-in and measurable. Model outputs create proposals, not self-verified organizational facts. |
| Retention policies and legal holds | Helps companies manage lifecycle obligations | Needs tenant policy, auditable holds, backup expiry and provider deletion semantics. Do not advertise legal compliance from a delete button alone. |
| OIDC/SAML, SCIM and group resolution | Reduces identity administration and enables provider groups | A high-priority enterprise extension. Until implemented and tested, unmapped/group-only provider grants remain denied. |
| Teams, OneDrive, SharePoint, Confluence, Notion, Jira | Common company knowledge sources | Add native adapters through the same contract. rclone covers supported storage objects, not every platform's permissions or collaboration semantics. |
| Slack/Teams interactive bots | Lets people capture and retrieve memory inside chat | Read-only ingestion is implemented first. Replies and workflow actions need explicit app permissions, caller identity and message review policies. |
| Webhooks and change feeds | Reduces polling and improves freshness | Authenticate signatures, reject replay, persist events before acknowledgment, reconcile periodically. A feed reporting “removed” may mean permission loss. |
| Encrypted object storage and external key management | Supports large evidence files and company infrastructure | Use a checksummed blob interface and a coordinated recovery protocol. A database transaction cannot atomically commit an arbitrary cloud object. |
| Offline capture queues | Helps intermittent hardware connections | Queue authenticated source observations locally, encrypt where required, reconcile versions on reconnect. Offline readers cannot receive immediate remote revocations. |

## Features to keep constrained

Do not make uncontrolled two-way folder/database sync, autonomous destructive
merging, or model-generated verification the default. They weaken the reliability
that makes shared memory useful. Keep prompt text from documents and messages as
untrusted evidence. Keep derived summaries and graph edges tied to live source
revisions, so an impressive visualization cannot bring back deleted or private
content.

The historical [landscape study](../research/2026-10-09-mnemion-study/LANDSCAPE.md)
contains the MemPalace and comparable-tool assessment. These decisions apply that
study to the expanded company/cloud requirements; they are not claims that all
optional integrations already exist.
