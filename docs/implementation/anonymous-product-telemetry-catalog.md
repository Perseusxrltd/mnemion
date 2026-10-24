# Proposed anonymous product telemetry catalog — V08

**Proposed catalog, recorded 23 October; source checkpoint 24 October 2026.**
This catalog supplements the [V08 contract](anonymous-product-telemetry.md).
Source now implements the [local privacy controls](../guides/product-telemetry-controls.md)
for app/native shared preference, browser-local choice, disclosure and company
restrictions. Collection remains unavailable, the destination is null, and no
product sender or collector is active. These controls do not implement the
measurements or settle ownership below. Metric names, workflow variants and
ownership rules remain proposals, with no accepted anonymity or native release
claim. **V08 is Building/source implementation and the active feature milestone**
after the accepted fresh backup and independent restore. All 66 requirement
texts and the other 65 states remain unchanged. The 19-check core browser journey
and eight further browser policy/fault checks have dated source evidence;
[source-input qualification](../validation/2026-10-24-telemetry-controls.md) passed
at **01:12:30 UTC**. Native acceptance remains open. These controls and this
documentation update are excluded from the isolated
4.46.6 dependency-security release.

The scope remains all app, agent and headless workflows. An unresolved row is
unfinished V08 coverage, not permission to collect without choice or an assertion
that client-only instrumentation completes “Full telemetry.”

## Measurement ownership

Count a logical workflow at one disclosed origin. A fixed surface enum describes
how it was invoked; it is not a user, installation or request identifier.

| Surface | Proposed owner and existing source boundary | Remote and nested work |
| --- | --- | --- |
| Desktop workspace UI | The top-level UI workflow using the [TypeScript client](../../packages/client/src/index.ts#L272), under the installation's shared policy. | [Native fetch](../../studio/frontend/src/workspace/native.ts#L2), transport retries and the remote API must not each add another usage count. |
| Browser workspace UI | The same UI workflow under browser-local disclosure, persistent choice, GPC and company restrictions. [Connect](../../studio/frontend/src/workspace/Connect.tsx#L145) also constructs the client before entering a workspace. | Workspace authentication is not product telemetry consent. Use a separate credential/referrer-free telemetry sender. |
| Native agent controlling the desktop | The shared desktop controller, with a fixed `native_agent` invocation surface. [Agent dispatch](../../mnemion/desktop_operator.py#L243) reaches the [desktop dispatcher](../../studio/electron/service-bridge.ts#L742); UI and agent host actions meet at [hostAction](../../studio/electron/service-bridge.ts#L304). | The agent pipe, renderer and controller must not all count the same action. They share effective local policy; no operation UUID enters telemetry. |
| Owned headless/CLI or local stdio-MCP client | A disclosed top-level agent context around [agent_control.execute](../../mnemion/agent_control.py#L224) or [MCP invocation](../../mnemion/service/mcp.py#L254), sharing local policy where applicable. | Generic SDK constructors default to no product measurement. The top-level context may supply a bounded local measurement sink; inner SDK calls are not new producers. |
| Third-party remote MCP or direct API client | **Unresolved coverage.** No product export for requests whose disclosure/choice is unknown. The [remote MCP gateway](../../mnemion/service/mcp_transport.py#L441) creates the ordinary [Python SDK Client](../../mnemion/sdk.py#L614). | A token, client name, session or host-owner preference cannot stand in for the originating user's choice. Instrumenting the generic SDK would also instrument this remote gateway. |
| Server jobs and autonomous host work | User-derived jobs remain part of their originating workflow. Separately disclosed host-owner measurement is a possible owner only for clearly autonomous maintenance. | [Index/purge jobs](../../mnemion/service/worker.py#L290), scheduled scans and mixed-host resource totals need explicit coverage decisions below. A `background` label does not make user-derived work autonomous. |

Future collection is enabled by default after the contract's required disclosure.
Per-installation choice does not imply an account-wide preference across other
installations. A persistent opt-out stops that installation's new collection and
emission, clears pending memory/disk aggregates, cancels retries and prevents a
shutdown flush. Every local producer and the final sender recheck effective
policy. Re-enable starts empty. Company policy may further restrict collection;
it cannot override user opt-out. Invalid or unreadable state suppresses emission.
These controls must work before sign-in, offline and through native-agent setup
and status. Already transmitted bytes cannot be recalled.

For the proposed originating-client boundary, services never export a replacement
count for the client's request or its derived jobs. Thus offline opt-out does not
depend on informing a remote server. Extending measurement to those services
would require a separate private choice/revocation and pending-data-clearing
design; a new header alone would not solve queued work or offline changes.
Existing authentication identities may remain in the operational control plane,
but never enter product queues, even hashed.

## Common bounded measurements and outcomes

The schema must enumerate exact feature/operation combinations from the next
table; arbitrary API paths, command names, labels and catch-all metadata are
forbidden. A producer accepts only selected numeric primitives and catalog enums,
never a request, result, exception, receipt or audit object.

| Proposed metric | Definition and bound to specify before implementation |
| --- | --- |
| `submissions`, `completions` | Separately clipped, bucketed counts of accepted submissions and actually observed terminal outcomes. Set a per-feature/window contribution cap; these are not people or device counts. |
| `latency_ms` | Sampled monotonic duration for a named logical boundary, including its internal retries. Finite clipping and histogram edges must be reviewed; a histogram yields bounds, not an exact percentile. |
| `result_items`, `work_items`, `queue_items` | Bucket existing numeric result, processed-item and backlog totals. Specify each denominator, sampling interval and cap; never export record/source identifiers. |
| `payload_bytes_sent`, `payload_bytes_received`, `stored_bytes` | Separate bucketed application-transfer and stored-size measurements from existing counters. They are not wire-byte totals. No re-reading content or files merely to measure their length. |
| `wire_bytes_sent`, `wire_bytes_received`, `throughput_bytes_per_second` | Only where the responsible transport can actually measure the stated basis. Distinguish payload from wire throughput; browser and subprocess gaps stay unavailable until measured. |
| `cpu_core_fraction`, `rss_bytes`, `resource_budget_bytes` | Coarse samples of CPU-time deltas per elapsed second, process RSS and configured resource budget. CPU can exceed one core; select finite caps and buckets without exporting hardware inventory. |
| `reported_tokens`, `queue_drops` | Clipped model-reported usage or local queue-drop counts, with fixed units and sampling basis. Token estimates must not be mixed with reported tokens. No extra model calls or collection while disabled. |

Only allowed combinations may form an aggregate cell. Platform/release-family
views and resource views stay separate, without join keys; they are not a full
cross-product with every operation, outcome and histogram. Missing sensors and
unobserved completion are `unavailable`, not zero or success.

Proposed fixed outcome vocabulary:

| Outcome | Meaning |
| --- | --- |
| `success` | The named boundary completed and its stated result was confirmed. |
| `accepted` | A submission was acknowledged; background completion is not implied. |
| `deferred` | Work is explicitly queued/paused or waiting on a known guard. |
| `cancelled` | Cancellation was confirmed, rather than inferred from a lost connection. |
| `denied` | The product operation was refused by its authorization or approval boundary. Telemetry opt-out itself produces no event. |
| `unsupported` | The current client/host lacks that operation. |
| `failed` | A failure was confirmed at the named boundary. |
| `unconfirmed` | The result of a submitted effect is uncertain and needs inspection. |

A separate, fixed reason enum may contain `none`, `invalid_input`,
`authorization`, `conflict`, `host_busy`, `resource_pressure`, `offline`,
`network_timeout`, `readiness_timeout`, `integrity_check`,
`recovery_required` and `other_failure`. Map reviewed domain codes to these
values; do not pass through arbitrary server codes or classify by parsing raw
exception text. A timeout after submission can be `unconfirmed`; it must not
become a claim that no effect occurred.

Count retries, status polling, cached replays and restored receipt inspection as
neither new submissions nor new completions. An asynchronous acknowledgement
is only `accepted`. If the origin does not observe terminal completion, leave
that measurement unavailable; do not backfill it from private server histories.
The future design must settle completion ownership across process restarts
without adding an operation identifier to product telemetry.

## Workflow catalog

Each family below expands only to its listed operation variants. Common
measurements apply where meaningful; additional numbers are also clipped and
bucketed. “Origin” means the disclosed app/agent owner above, not an arbitrary
caller of a shared SDK. Host/background entries stay withheld where ownership
or opt-out semantics are unresolved.

| Family and fixed operation variants | Proposed measurements and exclusions | Owner and current source |
| --- | --- | --- |
| `setup`: `create`, `configure`, `agent_install`, `agent_remove` | Submissions, confirmed completions and duration of local setup or agent configuration. Exclude owner/workspace names, settings bodies and credential provisioning data. | Origin, with local setup counted at its shared controller. [LocalSetup.perform/open](../../studio/frontend/src/workspace/LocalSetup.tsx#L49), [DesktopAgentSetup.install](../../studio/frontend/src/workspace/DesktopAgentSetup.tsx#L76). |
| `workspace`: `connect`, `sign_in`, `open`, `switch`, `disconnect`, `forget` | Connection/open outcomes and latency; a fixed local/remote mode only if needed in an approved view. Exclude addresses, identity providers, account names and saved-connection IDs. | Origin; [Connect.connect](../../studio/frontend/src/workspace/Connect.tsx#L145) and [workspace controller dispatch](../../studio/electron/service-bridge.ts#L784). |
| `memory`: `list`, `read`, `recall`, `context`, `knowledge`, `core_read` | Logical retrieval use, latency, result-count buckets and fixed empty/fallback/incomplete-index observations. Mode may be lexical/semantic/hybrid; no query, snippet, score vector, citation ID or search-filter values. | Origin; [SearchMemory.search](../../studio/frontend/src/workspace/Workspace.tsx#L1180), [Knowledge](../../studio/frontend/src/workspace/Knowledge.tsx#L17). [RetrievalService._measured](../../mnemion/service/retrieval.py#L118) is currently private operational measurement, not an export source. |
| `memory`: `save`, `revise`, `review`, `forget`, `core_write`, `import`, `export` | Submission/terminal outcomes, latency and bounded item/transfer totals. Distinguish accepted write from indexing readiness; preserve uncertain deletion outcomes. Exclude contents, review reasons, paths and idempotency keys. | Origin; [save/revise/forget UI](../../studio/frontend/src/workspace/Workspace.tsx#L753), [API write routes](../../mnemion/service/api.py#L616). Index/purge completion coverage remains open when the origin is absent. |
| `capture`: `configure`, `preview`, `collect`, `deliver`, `pause`, `drain`, `remove` | Separate local acceptance from remote delivery; bucket accepted/delivered counts, backlog, bytes and elapsed time. Fixed partial/fence/authorization reasons map into the common vocabulary. No conversation, file, device, grant or checkpoint identifiers. | Disclosed local capture owner; [shared native/headless cycle](../../mnemion/connectors/capture_cycle.py#L21), [DesktopSources](../../studio/electron/desktop-sources.ts#L362). The service must not recount accepted pages. |
| `sources`: `configure`, `scan`, `sync`, `pause`, `resume`, `repair`, `remove` | Scan/control outcomes, elapsed time and changed/removed/backlog buckets. Never export repository names, provider identities, paths, commits or per-source histories. | Origin for explicit controls; separately owned scans need local policy. [Connections](../../studio/frontend/src/workspace/Connections.tsx#L57), [runner._scan](../../mnemion/connectors/runner.py#L81), [managed status](../../mnemion/connectors/managed.py#L71). Shared-host scans remain unresolved. |
| `librarian`: `configure`, `run`, `cancel`, `accept`, `reject`, `undo` | Submission versus completion, duration, processed/skipped/proposal-count buckets and available reported-token totals. Exclude memory IDs, proposals, model/profile names and decision text. | Origin for controls; [Librarian.act](../../studio/frontend/src/workspace/Librarian.tsx#L145). [Scheduled runner](../../mnemion/service/librarian_runner.py#L81) completion and unattended work require the background ownership decision. |
| `models`: `configure`, `prepare`, `reindex`, `pause`, `resume`, `cancel` | Preparation/cache availability, downloads where measured, latency, admitted/deferred work and reported-token buckets. Use a reviewed local/remote execution class, not custom model IDs, endpoints, dimensions or exact hardware. | Origin for controls and owned local preparation; [EmbeddingModels](../../studio/frontend/src/workspace/EmbeddingModels.tsx#L33), [pinned model files](../../mnemion/service/model_files.py#L6), [ModelWorker](../../mnemion/service/model_worker.py#L25). Remote inference/background totals remain unresolved. |
| `backup`: `configure`, `create`, `list`, `verify`, `prune`; `recovery`: `inspect`, `restore`, `finish`, `discard` | Distinct submission, delivery, verified-readback and restore boundaries; duration and size buckets. Delivery includes upload/readback, and later verification downloads again. No destinations, key IDs, digests, archive names or operation IDs. | Origin through [local backup/recovery dispatch](../../studio/electron/service-bridge.ts#L650) or [HostBackups.request](../../studio/frontend/src/workspace/HostBackups.tsx#L24). [Native backup worker](../../mnemion/host_control/backup_jobs.py#L12) and [Git transfer stages](../../mnemion/host_control/backup_git.py#L263) are private evidence; remote completion ownership stays open. |
| `update`: `check`, `download`, `verify`, `apply`, `restart`, `rollback` | Confirmed stage outcomes, duration, transfer buckets and fixed restart/deadline reasons. A downloaded candidate is not an installed update; a rollback remains separate from success. Exclude exact version pairs, journal contents and idle/activity timelines. | Shared desktop updater policy: [check](../../studio/electron/updates.ts#L263), [guarded restart](../../studio/electron/updates.ts#L310). [Managed service update](../../mnemion/service/service_updates.py#L883) needs a disclosed host owner and background scope decision. |
| `host`: `adopt`, `enroll`, `inspect`, `start`, `stop`, `plan_upgrade`, `resolve`, `revoke` | Typed control use and confirmed outcomes, including busy/no-effect versus uncertain effects. Backup and update operations use their own rows, not another host mutation total. Never export host/operator identity, SSH fingerprints, signed plans or service paths. | Origin at [hostAction](../../studio/electron/service-bridge.ts#L304)/[HostProfiles.request](../../studio/electron/host-profiles.ts#L268); headless typed operations map through the [host protocol](../../mnemion/host_control/protocol.py#L153). |
| `evaluation`: `create_dataset`, `run`, `cancel`, `assess`, `compare`, `export`, `remove_dataset` | Workflow use, duration and case-count buckets. Quality-metric aggregation requires a separate reviewed view and remains undecided. No questions, reference labels, dataset names/IDs, per-case results or human notes; no extra evaluations or model calls for telemetry. | Origin at [Evaluations](../../studio/frontend/src/workspace/insights/Evaluations.tsx#L178). [EvaluationRunner._case](../../mnemion/service/evaluation_runner.py#L309) invokes retrieval with evaluation origin; those calls must not inflate interactive recall usage. [Ranking metrics](../../mnemion/service/evaluation_metrics.py#L13) remain private today. |
| `journal`: `configure`, `push`, `organize`, `backfill`, `recover` | Submissions, observed completion, duration and item-count buckets. No journal entries, repository destinations, source dates or replay identifiers. | Origin at [Journal.act](../../studio/frontend/src/workspace/Journal.tsx#L47), [JournalBackfill.act](../../studio/frontend/src/workspace/JournalBackfill.tsx#L35) and [recovery client methods](../../packages/client/src/index.ts#L192); unattended publication has the same unresolved background boundary. |
| `access`: `configure`, `invite`, `grant`, `revoke`; `vault`: `configure`, `read`, `write`, `delete`, `import`, `export` | Only fixed workflow/outcome counts and duration. Exclude values and value lengths, roles, identity/provider details, key names and all audit records. | Origin at [Team actions](../../studio/frontend/src/workspace/Workspace.tsx#L1944) and [SecretsVault.run](../../studio/frontend/src/workspace/SecretsVault.tsx#L45). Necessary private security records remain independent. |
| `resources`: `sample`; `bandwidth`: `sample`; `telemetry_queue`: `sample` | Coarse CPU/RSS/budget, queue/pressure, transport totals and telemetry drop/expiry buckets. No lifetime uptime, process IDs, exact timestamps or hardware profile. No opt-out/disable event. | One local sampler per measured scope under shared policy. [Process resources](../../mnemion/service/resources.py#L75), [memory budget](../../mnemion/service/memory_budget.py#L181), [inference queue](../../mnemion/service/inference_limits.py#L65) and [bounded stream reader](../../mnemion/agent_control.py#L160) provide techniques, not export-ready rows. Mixed-host totals and unmeasured wire traffic stay unresolved. |

A named subworkflow can have its own measurement, but its counts must not be
summed with its parent's as total independent uses. Background polling is not
feature adoption. This proposed family map still needs an explicit action-by-action
coverage reconciliation against the desktop, agent and public API catalogs.
Any unmapped action must appear as unmeasured in the local preview and remain a
coverage item; it must not fall into an arbitrary “other operation” event.

## Private operational metrics and remaining decisions

Current [Telemetry.record](../../mnemion/service/telemetry.py#L101) buffers
authenticating identity, tenant/space/generation IDs and minute timestamps.
[Identity](../../mnemion/service/db.py#L27) carries authorization, not telemetry
choice. Operational histories, source reports, host receipts and evaluations
are private product features governed by their own permissions. They cannot be
forwarded, scrubbed into a fallback feed or used to reconstruct opted-out use.
V08 disablement does not disable required access, recovery or security audit.
Even numeric process totals without identity labels can include opted-out users.

The following decisions remain **undecided**:

- **Remote-client coverage:** choose disclosed owned adapters or a service-side
  choice/revocation design for uninstrumented MCP/API clients. Unknown choice
  suppresses product export. An owner-enabled server does not authorize counting
  someone else's requests; a bearer token does not establish product consent.
- **Deferred and shared-host coverage:** define how a user opt-out applies to
  derived jobs, scheduled librarian/source work and shared CPU/RAM/bytes. Mixed
  totals cannot simply subtract opted-out contributions. Until isolation and
  semantics are established, withhold those exports; do not mark V08 complete.
- **Metric parameters:** select finite per-metric bounds, histogram edges,
  contribution caps, sampling rates, reporting windows, allowed cohort views
  and aggregate retention. The contract's existing queue/RAM/CPU/batch/wire
  ceilings remain acceptance ceilings, not a ready-made privacy mechanism.
  Evaluation-quality views and cross-restart completion measurement need review.
- **Anonymity and output:** substantiate ingress/provider log behavior, transient
  source-IP handling, metadata stripping and absence of retained raw events.
  Decide suppression/complementary-cell controls and whether local differential
  privacy, trusted aggregation or secure aggregation is needed. Protected unit,
  composition, privacy budget, minimum cohort rule and utility are not chosen
  here. Report counts cannot prove distinct contributors; a clean payload cannot
  prove network anonymity. No stable IDs may be introduced to fill these gaps.

Before launch, the contract requires actual sentinel/outbound and ingress-log
evidence, opt-out races and queue clearing across all producers, no nested SDK
or server recounting, unknown-client and deferred-job cases, resource/wire
measurements and cohort/linkage attacks. All six native targets and web need
their own policy journeys. No acceptance is supplied by this catalog, and no
collector, paid tooling or change to memory operation is authorized by it.
