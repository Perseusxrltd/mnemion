# Author withdrawal with protected derived-data erasure

Recorded **2026-10-12**. Published in **4.1.0** after all six installed upgrade
and recovery gates passed. Shared hosts still require the checked schema
migration before exposing this capability. Earlier candidate findings below
are retained as historical evidence.

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

The following sections preserve the earlier candidate findings. Final source
`4b5df29` passed all six installed upgrades and is now published; see
[final release acceptance](2026-10-12-v410-release.md). The original shared-host
schema migration and its Windows contributor lab remain separate pending work.

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
The [second matrix](https://github.com/Perseusxrltd/mnemion/actions/runs/38198627930)
reached the candidate inventory and rejected GitHub's provisional `untagged-*`
download addresses, again before installation. Draft validation now accepts that
repository-bound provisional address while requiring exact, unique asset API
identities, one consistent download identity, the pinned source commit and all
checksums. Published releases still require their ordinary tag URLs. All **12**
expanded safety checks and both actual 38-asset release inventories passed.
The corrected installed matrix still has to pass.

## Restored shared-host rehearsal

At **03:09:46 UTC**, the exact signed candidate was independently installed and
its source, wheel and installed package bytes verified on the existing remote
host without changing its live runtime or database.

At **03:11:06 UTC**, the candidate migrated only the previously restored isolated
copy from thirteen migrations to fourteen. All **50 existing data tables** kept
their pre-migration content hashes; reapplying the migration was a no-op. The
existing recovery login still authenticated, and copied production keys remained
revoked. A temporary contributor could access only its test space, save and
index its own note, withdraw it, replay the deletion receipt and observe physical
revision erasure. Authenticated API/MCP diagnostics passed; the temporary key was
revoked and the isolated supervisor shut down cleanly.

The original **4.0.14** service stayed ready with unchanged authority, schema and
runtime. This rehearsal made no production memory writes or cloud model calls.
Automatic updates were verified as the temporary host's default, then paused for
unpublished-candidate isolation; the real host's updater remained enabled.

## Remaining release acceptance

The [third installed matrix](https://github.com/Perseusxrltd/mnemion/actions/runs/38199057039)
passed the complete install/migrate/withdraw/restore workflow on Linux x64 and
ARM64. Both Windows targets reported a failure when reopening the candidate;
both macOS architectures timed out during candidate reopening. These are unresolved
installed-app findings, not accepted upgrades. The harness now offers focused
reruns and reads only bounded setup codes and code locations through a loopback
diagnostic connection on its disposable runner. It never exports raw exception
messages, connection strings, keys, profiles or backup contents. All **18**
inventory, execution-boundary and diagnostic-privacy checks passed.

The [focused Windows diagnostic](https://github.com/Perseusxrltd/mnemion/actions/runs/38200420078)
located the failure before migration: backup publication called `fsync` on a
read-only descriptor, which Windows rejects with `EBADF`. Three focused native
Windows regressions reproduced that error. The staged file now opens with write
access, without truncation, before flushing and exclusive publication. All four
native Windows tests passed after the change: verified archive round-trip,
complete recovery JSON, failure before publication when flushing fails, and
concurrent writers retaining exactly one winner. Linux also passed these checks
with the eighteen installed-harness checks. The new tests run in the native
client suite and the Windows private-state gate. They use disposable synthetic
files without starting a local model or changing the installed user profile.
The four archive checks and ten real-PostgreSQL recovery checks also passed
together under a 512 MiB / one CPU scope, including later deletion/access-ledger
reconciliation. No personal workspace was used.

This product fix changes package bytes. The original draft above remains
unpublished evidence; rebuilt and independently verified packages must pass
installed migration before publication. The macOS failure remains under
investigation.

A fresh original-host snapshot and ledger were encrypted and stored off-host at
**03:19:30 UTC**. Windows independently verified and decrypted both ciphertext
files at **03:23:21 UTC**, using its existing protected recovery identity;
**50,571,983 encrypted bytes** were checked without writing plaintext backups
or identity material on Windows. The original host still runs 4.0.14. This
snapshot is preserved, and the migration freshness guard must be satisfied again
after the installed-app findings are resolved.

Verify the contributor workflow in an isolated space on a migrated shared
workspace, including cleanup, without widening the agent's grant. Keep the
original host and its existing keys intact during coordinated migration.

The current compatible service patch channel deliberately refuses this schema
change. Automated migration-bearing fleet updates remain a separate requirement;
do not label an installed desktop update as a completed service migration.

## Final candidate accepted and published

The final source is `4b5df29131566e26b802ca8e4ef3fa77f06fc57e`. Its
[release run](https://github.com/Perseusxrltd/mnemion/actions/runs/38208553562)
passed all 30 jobs, and [installed upgrade/recovery](https://github.com/Perseusxrltd/mnemion/actions/runs/38211935149)
passed on Windows, macOS and Linux, both x64 and ARM64. Every target used its
actual previous installer and local model, preserved credentials/identities/
grants/memories, verified the automatic migration backup, migrated schema 13 to
14, withdrew and purged the existing contributor's note, reconciled current
deletions during isolated restoration and shut down cleanly.

At **06:24:43 UTC**, the exact signed final runtime also passed the restored
shared-host rehearsal. All 50 existing data-table hashes were preserved;
migration reapplication was a no-op, copied production credentials remained
revoked and recovery-administrator access remained valid. A temporary restricted
contributor passed save/index/withdraw/purge/replay and authenticated API/MCP
diagnostics, followed by credential revocation and clean isolated shutdown.
Production memory writes and cloud model calls were zero.

The final 38 assets and production update signatures were independently verified
and [published at 06:45:13 UTC](2026-10-12-v410-release.md). The original shared
host was still healthy on 4.0.14 at its latest direct observation. Its provider
control relay interrupted the operator connection before confirmed migration.
The verified **06:28:23 UTC** encrypted off-host backup and **06:31:18 UTC**
Windows decryption proof are preserved; the fifteen-minute freshness guard has
expired, so the operator must capture and verify a new backup before cutover.
Publication follows the requested policy of shipping verified targets while
continuing separate deployment acceptance; it does not claim that host migrated.
