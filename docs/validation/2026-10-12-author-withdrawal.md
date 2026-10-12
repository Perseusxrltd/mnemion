# Author withdrawal with protected derived-data erasure

Recorded **2026-10-12**. This is work for **4.1.0**, not a published capability.
The independently prepared 4.0.14 clock patch retains its original schema.

The initial regression reproduced issue 14: a contributor could save and revise
an ordinary note but could not withdraw it without reviewer authority. The
replacement authorizes the original contributor only when all content revisions
belong to that identity, the memory is ordinary and its current claim is not
verified. The API, SDK and MCP use the same transaction; Studio consumes the
optional `can_forget` observation instead of guessing from the current revision's
author field.

The investigation also verified that contributors cannot select protected
librarian dependency rows. Application-only cleanup would therefore miss them.
A new database trigger erases derived findings atomically with the memory
tombstone, scoped to the deleted memory's tenant and space. Direct execution of
the trigger function is not granted to the application role. Existing API and
worker roles remain separate from the schema owner.

## Completed source checks

Five initial tests failed before the change. The updated authorization,
transaction, HTTP and librarian tests pass **65 checks** against real PostgreSQL
using non-owner application and worker logins. The suite covers:

- An author's own corrections, immediate denial, physical purge and idempotent
  replay with the same or a new request key.
- Foreign authorship anywhere in the history, including an author editing again
  after someone else's change.
- Reader grants, quarantine, verified claims and removed access.
- Concurrent revision, quarantine, grant revocation and key revocation while the
  withdrawal waits for a memory-row lock.
- A reviewer's deletion remaining unauthorized to its original author after
  physical purge has erased the revision history.
- HTTP permission observations and the actionable `requires_reviewer` error.
- Immediate physical erasure of reviewer-only librarian suggestions, and rollback
  of that erasure when the containing deletion transaction fails.

Tests ran under a **512 MiB / one CPU** local scope. Embeddings were deterministic
transaction fixtures and librarian calls used an in-process HTTP transport
fixture. No local product model, listening service, personal workspace or cloud
model was used. These are correctness checks, not a retrieval-quality or hardware
performance benchmark.

A further **58 client, agent-contract, recovery, connector, export and reindex
checks** passed with the current Python/TypeScript clients. A separate previous-
schema upgrade check passed as well: it applied the preceding thirteen immutable
SQL migrations, created a workspace, contributor and memory, and checked that
the current runtime rejected that older schema. Applying only migration 014
preserved every existing table's content digest. The same owner and contributor
keys authenticated afterward and the contributor could withdraw its retained
note. Reapplying the migration was a no-op. These **124 automated checks** do not
substitute for an installed desktop or shared-host migration rehearsal.

At **01:56:26 UTC**, a fresh browser exercised the built UI with intercepted
synthetic HTTP contracts. Eligible authors saw withdrawal without quarantine
controls; Cancel made no deletion request, and confirmation sent the observed
version and an idempotency key. Ineligible authors and older servers received
no new author permission. Older-server reviewer controls remained usable.
Desktop and phone views were checked visually, without horizontal overflow or
browser errors. These are rendering/interaction checks; the real-database suite
above provides the separate authorization evidence.

The frontend and embedded documentation build also passed: **303 files,
2,640,900 bytes**, with 125 dependency-license components. Test browsers and the
disposable static server were closed after verification.

## Required acceptance

The [candidate release run](https://github.com/Perseusxrltd/mnemion/actions/runs/38195791683)
passed all **30 jobs**, including all six native targets. Its immutable source is
`2fd88c005743fe344b384d87c8869eb1a1d66f69`; subsequent test-harness and evidence
updates do not change those packages. All **38 assets, 3,863,359,063 bytes** were
downloaded independently. The complete checksum inventory, production
service/Windows/Mac signatures, packaged frontend and exact source commit agreed.
The checksum-file SHA-256 is
`eda0b59e8ae8470c4f3d24bd9901fba38b0d49ee0c14d81e355d44f2e10a0c06`.

Installed previous-version upgrade/recovery acceptance remains required before
publication.
The [installed upgrade workflow](../../.github/workflows/installed-upgrade.yml)
now provides the latter gate on six disposable native runners. It verifies a
published preceding installer and an exact, signed candidate; uses the installed
UI to create and reopen its real local workspace; checks preserved keys, grants
and memories; withdraws a note with the existing contributor; and restores the
automatic pre-migration backup with the current ledger into an isolated database.
Eight release-inventory and execution-boundary tests passed, including replaced
bytes, unpinned commits, unpublished predecessors, incomplete/redirected assets
and refusal to run on personal or persistent hosts. These eight harness
checks do not mean that the installed migration has passed; its native runs
remain required. Personal Windows profiles are not used; the real models run on
the disposable CI hosts.

The [first installed matrix](https://github.com/Perseusxrltd/mnemion/actions/runs/38198274221)
failed during release metadata retrieval, before application installation.
GitHub's read-only token omitted the unpublished draft, and Windows decoded
UTF-8 release metadata using CP1252. The harness now requests the repository
permission GitHub requires for draft access, disables checkout credential
persistence, and explicitly decodes GitHub output as UTF-8. The eight inventory
and execution-boundary checks passed again. Application children receive no
GitHub token; this workflow downloads releases and does not publish them.
The corrected native matrix still has to pass.

Verify the contributor workflow in an isolated space on a migrated shared
workspace, including cleanup, without widening the agent's grant. Keep the
original host and its existing keys intact during coordinated migration.

The current compatible service patch channel deliberately refuses this schema
change. Automated migration-bearing fleet updates remain a separate requirement;
do not label an installed desktop update as a completed service migration.
