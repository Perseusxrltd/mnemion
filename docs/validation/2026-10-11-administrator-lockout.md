# Independent administrator continuity and lockout protection

Validated **2026-10-11** against the 4.0.11 candidate. These checks are not a claim
that the behavior is in an earlier published desktop or separately hosted server.

The initial regression run reproduced nine failures: revoking the only admin
key succeeded, unusable administrator records counted as no protection, and
simultaneous revocations/disables could leave an organization without access.

The candidate serializes identity and credential changes per tenant using a
PostgreSQL transaction advisory lock. API and OAuth changes use the same lock.
It rechecks the caller after waiting, uses real time for credential expiry, and
rolls back removal of the final currently usable administrator credential.
The existing SQL migration files remain unchanged.

Real PostgreSQL with restricted application logins verifies:

- Rejection of final-key removal through the actual HTTP API, with continued
  authentication by the original key afterward.
- No fallback from an administrator without credentials, a disabled identity,
  or an expired/revoked key. Another tenant's administrator never counts.
- Successful rotation to a replacement key and idempotent repeated revocation.
- Concurrent self-revocation, mutual key revocation and mutual principal
  disabling leave one independently usable administrator.
- A key expiring after initial transaction authentication is rejected before
  the waiting administrative action can proceed.
- OAuth self-revocation cannot remove the final admin access; mixed OAuth/API
  races preserve one credential without removing ordinary member self-revocation.
- The independent administrator still receives no implicit memory-space grant.

The focused identity, transaction, OAuth and continuity run passed **77 tests**.
The full service regression run passed 502 tests and skipped five optional checks.
Its three environment failures were isolated: one required the installed `uv`
path and two setup fixtures needed more headroom than remained in that combined
512 MiB scope. All three passed with the configured tool path in a fresh bounded
scope, without changing application admission checks or the tests. In total,
**505 applicable service tests passed**, with five skips. All nine TypeScript
client tests and the production frontend build also passed.

Chromium used the real API and PostgreSQL to create a human administrator, issue
an individual key, reconnect without a content grant and open People & apps.
Canceling retirement left the original account usable. Confirming its retirement
through the app revoked its access while the new administrator stayed usable.
Final-key removal was rejected; after an explicit reader grant, the original
recorded evidence remained retrievable. A separate member application could not
escalate its role and lost access after its named retirement confirmation.
Desktop (1440×1080) and mobile (390×844) views were inspected. Small screens show
readable identity cards, and the page has no horizontal overflow or JavaScript
execution errors. Fixture keys and private screenshots are not committed.

The guard cannot verify possession of a key, availability of an external issuer,
future renewal, or the operator's ability to restart an unavailable machine.
Independent hosting, protected backups and owner/operator recovery remain
separate requirements in the [continuity contract](../implementation/workspace-continuity.md).
