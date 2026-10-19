<img src="studio/frontend/public/mnemion.svg" alt="Mnemion logo" width="72" height="72">

# Mnemion

[Current release status](docs/RELEASE_STATUS.md) · [Product roadmap](docs/ROADMAP.md) · [Complete requirements and progress](docs/PRODUCT_REQUIREMENTS.md)

Memory infrastructure for applications, teams, and AI assistants, with Obsidian
as a local visualization and inspection surface.

**100% free, always**, for individuals, teams and organizations. All features
and updates are included; optional [support](docs/SUPPORT.md) starts at €5 and
never gates downloads, usage or access.

**Mnemion 4.0 began the rebuilt shared-memory platform's v1 release line.**
Download current published builds from [the official product page](https://www.perseusxr.com/mnemion).
The automatically reconciled [release status](docs/RELEASE_STATUS.md) records
the version, available platforms and release-gate evidence. It distinguishes
published capability from the unfinished full product roadmap.
Desktop releases include [encrypted backups and independent
recovery](docs/service/native-backups.md); their published delivery evidence is
recorded in the release status above.
Studio includes guided [local workspace creation](docs/service/local-workspaces.md),
bundled database/model runtimes, [app and agent RAM controls](docs/service/memory-resources.md),
local recovery, a [live 3D memory map](docs/service/memory-map.md), recorded agent
activity and [connection diagnostics](docs/service/connection-diagnostics.md).
Set up [independent human administrators](docs/service/organizations.md#establish-independent-administrators)
to manage people, applications and space grants without the original agent.
The [continuity contract](docs/implementation/workspace-continuity.md) tracks the
remaining host delegation, independent recovery and company hosting workflows.
Published 4.2.0 includes [individual sign-in, invitations and device sessions](docs/service/sign-in.md),
with [six-platform installed migration and recovery acceptance](docs/validation/2026-10-13-personal-access-release.md).
Company accounts can use [Studio sign-in](docs/service/company-sign-in.md) from
4.9.0 and [assistant consent](docs/service/hosted-agent-sign-in.md) from 4.10.0;
the guides state their host configuration, validation and release requirements.
Source 4.11.0 adds [company-provider setup in the app](docs/service/company-sign-in.md#a-workspace-hosted-by-the-desktop-app),
including discovery, private client configuration, company certificates and local agent controls.
Source 4.12.0 adds a separate [encrypted credentials vault](docs/service/secrets-vault.md)
with app setup, individual grants, access auditing, encrypted export and independent
key recovery. Credentials stay outside searchable memory and Obsidian exports.
Studio retains OS-protected saved connections, identity-checked reopening after restart and a clearer connection
screen. [Workspace controls](docs/service/workspaces.md) explain remembering,
disconnecting and forgetting a device connection. Complete fresh-machine setup
through the app remains [active work](docs/implementation/app-onboarding.md).
The Perseus XR design and [signed Linux/macOS service updater](docs/service/managed-updates.md)
include backup verification and data-preserving rollback.
Official Python packages include web Studio, local fonts and offline guides.
Source-sync controls, agent administration, Obsidian compatibility and the earlier
native-update and model-memory improvements are retained.
Source 4.15.0 adds optional [Git journals](docs/service/git-journal.md) for future
native memory changes, with publication consent, guarded delivery and complete
source replay. Source 4.16.0 adds scheduled filing into Obsidian-readable notes
and intact archival, with app and agent controls. Git history retains published
text; journals do not replace a full workspace backup. Source 4.18.0 adds local
desktop host registration and matching agent controls. Git sign-in, guided remote
host enrollment, backfill and large-history scaling remain on the roadmap.
Source 4.19.0 adds [daily journal rollover and cached retries](docs/service/git-journal.md#file-rollover-and-version-compatibility),
plus [local agent update controls](docs/service/desktop-operator.md#app-updates-and-startup).
Upgrade journal-reading runners as well as publishers before using continuation
files. Complete inventory limits and independent remote hosting still apply.
Source 4.17.0 adds [live JSONL conversation capture](docs/service/live-conversations.md):
bounded records and fragments, deferred tails, per-file source controls, private
checkpoints, unchanged-fragment reuse and capture progress in the app. Existing
complete-file and Git-journal safeguards remain in force.
Release targets cover **Windows, macOS and Linux on x64 and ARM64**. Windows and
Mac updates use independent publisher signatures. The product page lists only
published, verified builds. Development and
current documentation live on `main`.
Implementation, measured results, native checks and remaining acceptance work
are tracked in [the release ledger](docs/implementation/v4_progress.md).
The full codebase study, design decisions, and rebuild map are preserved in
[the research report](docs/research/2026-10-09-mnemion-study/README.md).

Mnemion gives each application a credential and explicit access to memory spaces.
It retains source evidence and immutable revisions, supports corrections and
review, and enforces current access and deletion policy when returning results.
An authenticated identity is separate from the person or project a memory is about.

## Included

- PostgreSQL with pgvector and lexical search, durable ingestion receipts,
  background indexing, retries, and deletion jobs.
- Pinned local multilingual embeddings, scoped hybrid recall, source citations,
  temporal filters, and bounded context packs.
- A versioned HTTP API, [OpenAPI contract](docs/service/openapi.json),
  Python and TypeScript clients, and authenticated MCP with stdio and Streamable
  HTTP; API and HTTP MCP share one listener by default.
- [Agent administration](docs/service/agent-control.md): a reviewed operation catalog,
  an offline catalog/CLI, compact MCP tools, private results and safe retry rules.
- Studio for saving, searching, inspecting evidence and revisions, reviewing
  memories, managing identities/grants, and tracking indexing/deletion activity.
- [Personal and company agent sign-in](docs/service/hosted-agent-sign-in.md): explicit consent,
  scoped account authority, rotating OAuth credentials and connected-app revocation.
- [Visual insights and evaluations](docs/service/insights.md): resource and retrieval
  diagnostics, private versioned test sets, bounded runs, comparisons and exports.
- [Configurable librarian](docs/service/librarian.md): approved local/cloud models,
  bounded schedules, source-linked organization proposals, human review and undo.
- [Desktop background operation and automatic updates](docs/service/updates.md),
  with login startup and safe idle restarts on supported installer formats.
- [Managed server updates](docs/service/managed-updates.md) for compatible Unix
  service patches, with private host controls, backup verification and rollback.
- Standard Obsidian Markdown, YAML, wikilinks, source anchors, native graph
  navigation, stable existing note paths, and conflict-aware local refresh.
- [Source connections](docs/service/connectors.md) for Git, Google Drive, Slack,
  selected folders/vaults, rclone-supported storage and custom company adapters,
  with durable sync requests and timestamped scan diagnostics.
- [Conversation capture](docs/service/capture.md), [agent setup](docs/service/agents.md),
  and an evidence-linked [wiki, graph and curation view](docs/service/knowledge.md).
- Complete versioned service backup/restore and v3 preservation tools, with
  current deletion-ledger reconciliation before a recovered database is published.

## Run the service

For a workspace on your own computer, install the desktop and choose **Create
on this computer** (4.0.11 or later). Follow the guided model, resource and
workspace checks; Python and Docker are not required. To join an existing team,
use its workspace address and your individual credential.

For an independently hosted team service, follow the
[Docker setup and operations guide](docs/service/deployment.md). It includes
private initialization, Studio, model preparation, backups and verified recovery
cutover on Windows, macOS and Linux.

Use Python 3.12–3.14, Node.js 22+ for Studio/TypeScript development, and PostgreSQL
with pgvector. Intel Mac servers use Python 3.12 or 3.13 because their compatible
ONNX runtime has no Python 3.14 wheel. The example selects 3.13:

```sh
uv sync --locked --python 3.13
uv run mnemion-service --help
```

Follow [the service setup guide](docs/service/README.md) to migrate the database,
provision separate API and worker logins, create an organization/private space,
and start the service. Administration credentials stay with setup and recovery;
API and worker processes use their restricted logins.

Official Python release packages include Studio. For a Git checkout, run
`uv run --no-sync mnemion-service studio build` before starting the API. The web UI
then opens at the service's `/workspace`; `studio status` reports its availability.

A local model must be prepared before semantic indexing. Lexical retrieval and
write receipts expose readiness explicitly. Failed model preparation never
substitutes a synthetic embedding.

## Connect applications and assistants

```python
from mnemion.sdk import Client

with Client("http://127.0.0.1:7892", api_key) as memory:
    receipt = memory.save(
        space_id,
        "Keep Obsidian for visualization of shared memory.",
        idempotency_key="project-decision-42",
        subject="Mnemion",
    )
    evidence = memory.search("How do we inspect project memory?", [space_id])
```

The [service guide](docs/service/README.md) includes TypeScript usage;
[agent setup](docs/service/agents.md) covers current MCP clients and configuration previews.
Give each integration its own key and only the space grants it needs. A write
receipt acknowledges durable acceptance; its operation reports indexing progress.

## Obsidian

Open Studio's Obsidian view to download a scoped ZIP, or refresh an existing local
vault with the CLI/client. Existing generated note paths stay stable even when a
title changes. New notes use readable graph labels. Refresh preserves personal
sections and `.obsidian` settings, records conflicting edits, and prunes only known
managed content.

[Scheduled vault refresh](sync/README.md) uses an authenticated reader credential.
Obsidian files remain ordinary Markdown; no Mnemion Obsidian plugin is required.

## Organization boundaries

Deploy one service for an organization and grant each person, application and
agent its own identity. Create spaces for departments, projects, clients and
private work. Access is checked when reading, writing, searching, exporting,
evaluating and deleting. Source connections are scoped to spaces; connecting a
cloud account does not make its contents visible to the whole organization.
See [organization deployment and vault security](docs/service/organizations.md).

## Existing v3 installations

Preserve and rehearse recovery before migration. Use the
[versioned backup and recovery guide](docs/service/recovery.md); a drawer JSON
export lacks source files, history, core blocks, and vault settings. The compatible
JSON importer validates the complete input and sends new records without lifecycle
information to review.

Automated Git array/SQL merging is retired because it could resurrect deleted
records. Use the service for shared memory and explicit local vault refresh for
Obsidian. The original v3 guide and changelog remain in
[the historical documentation](docs/legacy/v3-readme.md).

## Development and support

```sh
uv sync --locked --extra legacy --group dev
npm --prefix packages/client ci
npm --prefix packages/client test
uv run python -m pytest service_tests tests
npm --prefix studio/frontend ci
npm --prefix studio/frontend run build
```

Service tests use a disposable real PostgreSQL instance with pgvector. Set
`MNEMION_TEST_ADMIN_DSN` for an external test database; Python 3.12 Linux development
can also use the optional bundled test server. Recovery tests need PostgreSQL
client tools. Real-model tests additionally use `MNEMION_TEST_LOCAL_MODEL=1` and a
prepared `MNEMION_MODEL_CACHE`.

Report reproducible problems through [GitHub issues](https://github.com/Perseusxrltd/mnemion/issues).
Include the service version, failing operation/error code, and steps to reproduce;
keep credentials and private memory content out of public reports.

Mnemion retains its MemPalace lineage and attribution. See [LICENSE](LICENSE) for
the MIT license. The study distinguishes upstream design inspiration from features
and performance independently verified in this implementation.

## Documentation and roadmap

Open **Documentation & roadmap** in Studio, or use the setup screen’s help link.
The offline library ships the same Markdown as this repository. See the
[product roadmap](docs/ROADMAP.md), [current release notes](https://github.com/Perseusxrltd/mnemion/releases/latest), and
[documentation maintenance policy](docs/MAINTENANCE.md). Every release and hotfix
must include matching release notes and a reviewed roadmap.

## Code signing policy

See the [code signing policy](docs/CODE_SIGNING.md) for signing status, release
roles and verification requirements, and the [privacy policy](docs/service/privacy.md)
for network connections, storage and user controls. Mac updates use independently
signed Ed25519 archives with a validated Sparkle/Electron integration; first
installation may need Privacy & Security approval. Windows updates authenticate
signed Ed25519 manifests; the first installer can show an unknown-publisher prompt
while SignPath approval is pending. CI-only packages are not published downloads.
