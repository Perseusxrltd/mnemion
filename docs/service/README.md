# Mnemion shared service

This is the **4.0 shared-memory service**. It provides authenticated spaces,
versioned source evidence, durable indexing, local multilingual search, HTTP and
MCP access, and Obsidian exports. The [product page](https://www.perseusxr.com/mnemion)
provides desktop downloads for Windows, macOS and Linux on x64 and ARM64. The
[release notes](../releases/4.0.7.md) describe the current package changes and
remaining work. Complete backup/recovery, v3 import with cutover and rollback,
and Studio are implemented. Larger concurrent-capacity measurements and managed
server updates remain on the roadmap.

Use the [Compose deployment guide](deployment.md) for packaged initialization,
private runtime credentials, a shared Studio service, operations, and recovery
cutover. The commands below cover a standalone or managed PostgreSQL installation.

## Run the service

Use Python 3.12–3.14 (3.12/3.13 on Intel Macs) and a dedicated PostgreSQL database with the `vector` extension
available. Migration credentials need permission to install the extension,
create the Mnemion schema, and create database roles. API and worker processes
use separate restricted logins; startup rejects an owner or superuser login.

Install from a tagged release checkout, or use `main` for current development:

```bash
uv sync --locked --no-dev --python 3.13
```

Set `MNEMION_ADMIN_DATABASE_URL` to your database administration connection
string. Keep it out of application and worker configuration. Provision the schema
and restricted logins, then create your first organization and private space:

```bash
uv run --no-sync mnemion-service migrate
uv run --no-sync mnemion-service logins --output .mnemion-run/database.mnemion-credentials.json
uv run --no-sync mnemion-service bootstrap \
  --tenant "My team" --owner "Owner" --space "Private memory" \
  --output .mnemion-run/owner.mnemion-credentials.json
```

The login command creates `mnemion_api_login` and `mnemion_worker_login` by
default; use `--prefix` for another deployment in the same cluster. It refuses
to overwrite an existing credentials file or existing login. The bootstrap
command creates a new organization on every successful invocation. It writes
the one-time owner API key to the specified file, and prints only the file path
and organization/space identifiers. Protect both credentials files.

Run the API and worker in separate processes:

```bash
uv run --no-sync mnemion-service \
  --credentials .mnemion-run/database.mnemion-credentials.json serve

uv run --no-sync mnemion-service \
  --credentials .mnemion-run/database.mnemion-credentials.json worker
```

For persistent background operation on Linux or macOS, use the
[Supervisor setup](supervision.md). It works without systemd, keeps the two role
credentials separate, restarts crashes, and generates cron/launchd startup
configuration. Windows uses the [Compose deployment](deployment.md).

The API listens on `127.0.0.1:7892`, with authenticated MCP at `/mcp`. Studio opens
at `/workspace`; interactive API documentation is at `/docs`. Use `serve --host` and `--port` to
configure the listener. For network deployment, put the API behind a TLS proxy
and configure allowed browser origins with `MNEMION_CORS_ORIGINS`.

The worker downloads and verifies the pinned multilingual E5 small ONNX model
when first needed. No paid model key is needed. Prepare the cache explicitly with:

```bash
uv run --no-sync mnemion-service prepare-model
```

`MNEMION_MODEL_CACHE` selects the cache location; `MNEMION_MODEL_OFFLINE=1`
requires the files to be present already. `MNEMION_MODEL_THREADS` defaults to 2.
The API and worker must use the same approved model configuration. Each space
can select a generation through a controlled candidate reindex. The generation
includes the model revision, tokenizer/model hashes, dimensions, query/document
prefixes, pooling, normalization, and chunking configuration.
See [embedding models](embeddings.md) for the small English CPU option, approved
local/cloud endpoints, per-space egress approval, comparisons and rollback.

The optional [memory librarian](librarian.md) uses separately approved local or
cloud language models for titles, tags, summaries and review findings. Configure
its endpoint on the API host, then enable it per space in Studio. It has bounded
jobs, optional schedules, durable daily call limits, evidence checks and human
review; no language model or schedule is enabled by default.

## Studio

Official Python wheel and source archives from **4.0.6** include the matching
web Studio, offline guides, roadmap and dependency notices. Installing one of
these packages needs no Node.js or separate UI build. `mnemion-service serve`
automatically serves the bundled UI. It still needs the database/runtime setup
above; installing a Python package does not provision PostgreSQL.

A Git checkout contains frontend source. Install Node.js **22 or later** with
npm and run this single command from the checkout before starting the service:

```bash
uv run --no-sync mnemion-service studio build
```

The command installs locked SDK/frontend dependencies, builds the web UI and
documentation, collects licenses, checks the bounded file inventory, then
replaces the generated bundle. A failed build keeps the previous complete bundle.
Build before starting or restarting the API; this command does not restart a
running server. Builds cannot run concurrently in one checkout. After an abrupt
process kill, remove `build-tmp/web-studio.lock` only after confirming its recorded
builder PID is no longer running.

Use `mnemion-service studio status` to inspect the selected UI without database
credentials. Source startup explains the build command when no UI is available.
Use `serve --no-studio` or `MNEMION_STUDIO_ENABLED=0` for an intentional API/MCP-only
deployment. `serve --studio PATH` and `MNEMION_STUDIO_DIST` retain explicit override
support; an invalid selected build fails clearly. A normal frontend development
build in `studio/frontend/dist` is also detected when no packaged bundle exists.

Open `http://127.0.0.1:7892/workspace`, enter the service address and a scoped API
key, and use the workspace to save, revise, review, search, build context, inspect
evidence, manage applications/access, follow ingestion activity, and export to
Obsidian. Keys stay in window memory; reconnect after a reload. Downloadable
original source attachments include hashes that Studio verifies before saving.

The [desktop client](updates.md) connects to the same service. It adds
a native vault picker and applies authorized Obsidian exports using a packaged
local client. The desktop connection does not require browser CORS exceptions or
a separate Chroma/model installation. The new desktop defaults to the shared
workspace; legacy Studio is a separate development compatibility mode.

## Use it from an application

The Python client uses the same HTTP contract as other programs:

```python
import json
from pathlib import Path
from mnemion.sdk import Client

owner = json.loads(Path(".mnemion-run/owner.mnemion-credentials.json").read_text())
with Client("http://127.0.0.1:7892", owner["api_key"]) as memory:
    receipt = memory.save(
        owner["space_id"],
        "Billing backups are retained for thirty days.",
        subject="Billing service",
        idempotency_key="billing-policy-2026-10-09",
        source={"title": "Billing retention decision", "uri": "https://example.com/decisions/42"},
    )
    results = memory.search("How long are billing backups retained?", [owner["space_id"]])
    for hit in results.hits:
        print(hit.text, hit.evidence.source_revision_id)
```

`accepted` means the source, memory revision, lexical index, audit event, and
indexing job committed together. Use `memory.operation(receipt.operation_id)`
or `memory.wait(...)` for semantic indexing completion. A wait can return
`failed` or `cancelled`, or raise a timeout; callers must handle those states.

The TypeScript client is in `packages/client`:

```ts
import { MnemionClient } from '@mnemion/client'

const memory = new MnemionClient({ baseUrl, apiKey })
const receipt = await memory.save(spaceId, {
  content: 'Billing backups are retained for thirty days.',
  subject: 'Billing service',
}, 'billing-policy-2026-10-09')
const results = await memory.search({ query: 'billing backups', space_ids: [spaceId] })
```

Each client retains one idempotency key across a retry. A reused key with a
changed payload receives `409 idempotency_conflict`. Revision writes require
`expected_version`; omitted subject, metadata, kind, and validity fields are
preserved. Explicit null/empty values change those fields. Previous source and
memory revisions remain traceable until authorized deletion.

## Applications, people, and spaces

Create a principal with `POST /v1/principals`, create its API key with
`POST /v1/principals/{id}/keys`, and grant a role with
`PUT /v1/spaces/{space_id}/grants/{principal_id}`. A new principal has no content
access until granted. API keys are returned once at creation; later key lists
contain prefixes and expiry/revocation metadata. Only their digests are stored.

| Role | Content operations |
| --- | --- |
| Reader | Recall, fetch, context, ordinary exports |
| Contributor | Reader operations plus observed-memory saves and corrections |
| Reviewer | Contributor operations plus verification/lifecycle changes, quarantine review, deletion, and core blocks |
| Space administrator | Reviewer content permissions; organization administration remains separate |

An organization administrator manages principals, keys, and grants. It still
needs a space grant to read that space's content. A memory's `subject` is the
entity it describes; `created_by` comes from the authenticated principal.

## Connect an assistant

Use the maintained MCP 2.x implementation through stdio:

```json
{
  "mcpServers": {
    "mnemion": {
      "command": "/path/to/.venv/bin/mnemion-service",
      "args": ["mcp"],
      "env": {
        "MNEMION_API_URL": "http://127.0.0.1:7892",
        "MNEMION_API_KEY": "YOUR_APPLICATION_KEY"
      }
    }
  }
}
```

Use [Agents & apps and the safe setup command](agents.md) for client-specific configuration.
The ordinary tools are `memory_spaces`, `memory_save`, `memory_search`, `memory_fetch`,
`memory_context`, `memory_map`, `memory_revise`, and `memory_forget`. Saves and revisions take
an explicit idempotency key. Memory content is evidence, not an instruction
channel. MCP registration does not install capture hooks or imply automatic
conversation capture.

The API now serves authenticated Streamable HTTP MCP on the same port by default:

```bash
uv run --no-sync mnemion-service serve
```

Use `http://127.0.0.1:7892/mcp` for MCP and `http://127.0.0.1:7892/v1/` for
HTTP operations. Every MCP request, including initialization and tool discovery,
requires the caller's valid Bearer API key; it cannot fall back to a configured
stdio/owner credential. Revocation is checked on subsequent requests.
For a TLS proxy or tunnel, configure `serve --public-url https://memory.example.com`
so MCP accepts the exact public host/origin. See [remote agent setup](agents.md#remote-http-connections).

`serve --no-mcp` disables the combined endpoint. The standalone command
`mnemion-service mcp --transport streamable-http` remains available on port 7893,
with the same `--public-url` option. Tests exercise both current discovery and
older initialization flows. OAuth browser sign-in is not implemented yet.

`mcp --legacy-space SPACE_UUID` also exposes compatibility names for drawer
save/search/delete and Open Brain capture/search/list/stats/search-fetch. Wing
and room filters are metadata within that configured space. These adapters
return canonical UUIDs and resolve imported v3 IDs within the configured space.
The [migration guide](migration.md) explains aliases, raw source evidence,
cutover, and the preserved legacy graph/wiki archive. Original local tools
remain available through the Python 3.12 `legacy` extra.

## Obsidian

Refresh a local vault with the owner or application credential:

```bash
uv run --no-sync mnemion-service \
  --credentials .mnemion-run/owner.mnemion-credentials.json \
  vault --path ./My-memory-vault --spaces SPACE_UUID
```

Set `MNEMION_API_URL` for another API address. `--dry-run` inspects a refresh;
`--open` opens a successfully refreshed vault in Obsidian. Reviewer exports
require `--review` and reviewer access to every selected space. The HTTP
`POST /v1/exports` endpoint provides the same ZIP without accessing desktop files.

The vault contains standard YAML/Markdown, stable memory paths, entity and space
indexes, source citations, revision notes, and wikilinks for the native graph.
No community plugin is required. Add your text under **Personal annotations**
or outside the generated markers. Those sections are preserved byte-for-byte.
Unmanaged notes and `.obsidian` settings are not refreshed or pruned.

An edit inside a generated section produces a proposed replacement in
`.mnemion-conflicts`, preserves the original, and leaves the completed watermark
unchanged. Review the proposal and reconcile the original before retrying.
Unknown legacy files likewise require review when their ownership cannot be
established by hashes. When a known generated memory is withdrawn, its generated
content is removed and any annotations remain as an unmanaged note at the same
path. An interrupted refresh retains intended hashes for the next reconciliation.

A vault is bound to its exported tenant, spaces, and ordinary/review policy.
Use a separate destination for another scope. Offline copies reflect their last
successful refresh; the service cannot recall content a person copied elsewhere.

## Sources, capture and organized knowledge

Use [Connections](connectors.md) for selected vaults, Git, Google Drive, Slack,
rclone-supported clouds and custom company adapters. The [capture guide](capture.md)
explains optional conversation normalization and session hooks. [Wiki & graph](knowledge.md)
provides current evidence-linked topics, relationships and review suggestions.

## Operations and limits

`/health/live` reports process liveness. `/health/ready` checks database access
and the configured model generation. Readiness does not imply that a worker is
running or that every memory is semantically indexed. Per-space status and
operation receipts expose that distinction. Worker lease recovery, retries,
terminal failures, and reviewer-triggered retries are implemented.

The initial retrieval engine uses PostgreSQL text search and **exact**, scoped
vector distances with rank fusion. It does not yet claim approximate-index
performance at large scale. Scores describe relevance, not truth probability.
Context packs count their complete rendered text with the selected tokenizer
or explicitly labelled UTF-8 byte budgeting. They report `token_count_unit`, the
tokenizer and generation. Cross-generation context uses byte budgeting;
applications must account for their answering model and surrounding prompt.

Current limits include 65,536 characters per memory, a 2 MB request body, 50
recall results, and 1,000 explicitly selected spaces. `all_accessible: true` resolves up to 10,000 current readable scopes. Obsidian artifacts are limited to 10,000
memories and 100 MB of captured record data. See [complete backup and recovery](recovery.md)
and [v3 migration, cutover, and rollback](migration.md). An Obsidian ZIP is an
authorized visualization export and cannot substitute for a database backup.

Run developer checks with PostgreSQL integration tooling and the legacy adapter:

```bash
uv sync --locked --extra legacy --group dev
uv run --no-sync pytest
MNEMION_TEST_LOCAL_MODEL=1 MNEMION_MODEL_CACHE=/path/to/model-cache uv run --no-sync pytest service_tests
cd packages/client
npm ci
npm test
```

Service tests use an isolated PostgreSQL database. Set `MNEMION_TEST_ADMIN_DSN`
to a disposable test cluster, or use the development-only `pgserver` dependency
on Linux/macOS. Its bundled database is test tooling, not a production distribution.
