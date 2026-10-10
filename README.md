# Mnemion

Memory infrastructure for applications, teams, and AI assistants, with Obsidian
as a local visualization and inspection surface.

**100% free, always**, for individuals, teams and organizations. All features
and updates are included; optional [support](docs/SUPPORT.md) starts at €5 and
never gates downloads, usage or access.

**Mnemion 4.0 is the first release of the rebuilt shared-memory platform.**
The [release notes](docs/releases/4.0.0.md) describe its scope and current shipping
status. Implementation and acceptance are tracked in [the release ledger](docs/implementation/v4_progress.md).
See the [current validation report](docs/validation/2026-10-10.md) for measured
retrieval results, native checks and remaining limits.
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
  Python and TypeScript clients, and an MCP gateway with stdio and Streamable HTTP.
- Studio for saving, searching, inspecting evidence and revisions, reviewing
  memories, managing identities/grants, and tracking indexing/deletion activity.
- [Visual insights and evaluations](docs/service/insights.md): resource and retrieval
  diagnostics, private versioned test sets, bounded runs, comparisons and exports.
- [Configurable librarian](docs/service/librarian.md): approved local/cloud models,
  bounded schedules, source-linked organization proposals, human review and undo.
- [Desktop background operation and automatic updates](docs/service/updates.md),
  with login startup and safe idle restarts on supported installer formats.
- Standard Obsidian Markdown, YAML, wikilinks, source anchors, native graph
  navigation, stable existing note paths, and conflict-aware local refresh.
- [Source connections](docs/service/connectors.md) for Git, Google Drive, Slack,
  selected folders/vaults, rclone-supported storage and custom company adapters.
- [Conversation capture](docs/service/capture.md), [agent setup](docs/service/agents.md),
  and an evidence-linked [wiki, graph and curation view](docs/service/knowledge.md).
- Complete versioned service backup/restore and v3 preservation tools, with
  current deletion-ledger reconciliation before a recovered database is published.

## Run the service

For a complete local or team deployment, follow the
[Docker setup and operations guide](docs/service/deployment.md). It includes
private initialization, Studio, model preparation, backups and verified recovery
cutover on Windows, macOS and Linux.

Use Python 3.12–3.14, Node.js 22 for Studio/TypeScript development, and PostgreSQL
with pgvector. From this checkout:

```sh
uv sync --locked
uv run mnemion-service --help
```

Follow [the service setup guide](docs/service/README.md) to migrate the database,
provision separate API and worker logins, create an organization/private space,
and start the service. Administration credentials stay with setup and recovery;
API and worker processes use their restricted logins.

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
[product roadmap](docs/ROADMAP.md), [release notes](docs/releases/4.0.0.md), and
[documentation maintenance policy](docs/MAINTENANCE.md). Every release and hotfix
must include matching release notes and a reviewed roadmap.

## Code signing policy

See the [code signing policy](docs/CODE_SIGNING.md) for signing status, release
roles and verification requirements, and the [privacy policy](docs/service/privacy.md)
for network connections, storage and user controls. Native validation builds are
not trusted, signed production releases. Free open-source signing is under review.
