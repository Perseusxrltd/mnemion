# Withdraw an authored memory

Service **4.1.0** lets a contributor withdraw their own memory without giving
that person or agent reviewer access to everyone else's notes. This addresses
[issue 14](https://github.com/Perseusxrltd/mnemion/issues/14).

An author can withdraw a memory only while all these conditions hold:

- Their current space grant permits contributions.
- The memory is ordinary, its current claim is not verified, and that identity
  originally created it.
- Every recorded content revision was made by that same identity. Revising
  somebody else's note, or editing again after another person's revision, does
  not make it eligible.

Reviewers retain their existing lifecycle authority within their granted spaces.
Organization-administrator status alone does not give content access. Quarantined
memory remains unavailable to ordinary contributors. Reader access, expired or
revoked keys, removed grants and another tenant's identity do not authorize a
withdrawal.

## App and agent controls

Open a memory in Studio. Eligible authors see **Withdraw your memory** and a
named confirmation. Reviewers retain **Review & lifecycle**. Earlier servers
continue to expose their existing reviewer controls; installing a new desktop
does not silently change a shared server's permission policy.

`GET /v1/memories/{memory_id}` returns optional `can_forget`. It describes the
current permission for that fetched memory. Missing or null means this response
does not provide the observation; it does not mean permission has been granted.
Lists and historical views need not carry it. The field does not reserve a
permission or bypass a later edit, quarantine or revocation.

Use the existing `memories.forget` agent operation, MCP `memory_forget`, Python
`Client.forget`, TypeScript `client.forget`, or
`DELETE /v1/memories/{memory_id}?expected_version=...`. Preserve the same
idempotency key when retrying the same request. A visible memory outside the
author rule returns `403 requires_reviewer`; an inaccessible or quarantined
memory retains its non-disclosing unavailable response. A reader still needs a
write grant. Changes to a note's subject or text do not change its authenticated
author identity.

## What happens to the data

The transaction rechecks authority after idempotency and memory-row lock waits.
Withdrawal denies future content reads immediately, cancels obsolete indexing,
records the access/deletion ledger and queues physical purge. Existing source,
search, export and recovery rules remain in effect.

Librarian findings can contain prose derived from a note that the contributor
cannot inspect. Migration `014_author_withdrawal.sql` installs a narrowly scoped
database trigger which invalidates and erases those derived findings in the
same transaction as the memory tombstone. It exposes no new read privilege or
callable cleanup operation to contributors. A failed transaction rolls back both
withdrawal and derived erasure. The worker still completes the ordinary physical
purge afterward.

After purge, a contributor's own deletion receipt permits an idempotent replay.
Empty revision history does not authorize replay of another person's deletion.
Current membership and credential validity are still required. Copies exported
outside Mnemion retain the existing limits described in the
[organization guide](organizations.md).

## Upgrade and validation

This feature requires service 4.1.0 and its checked database migration. Back up
the database and current recovery ledger, stop the previous service, apply the
matching migration with the operator credential, then start the new runtime and
verify identities and grants. Do not give the ordinary API or worker an owner
database login. The [managed patch policy](managed-updates.md) intentionally does
not apply a migration-bearing or different-minor release automatically.

The [validation record](../validation/2026-10-12-author-withdrawal.md) distinguishes
source checks from native release and real shared-workspace acceptance. It does
not claim that 4.1.0 is already published.
