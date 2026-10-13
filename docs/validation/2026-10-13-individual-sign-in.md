# Individual sign-in validation — 2026-10-13

This is unreleased implementation and acceptance work on
`codex/individual-signin`, beginning with checkpoint `70f0fbc`. It does not
change the published product's completion count or claim that individual
sign-in, company SSO or hosted OAuth is available in 4.1.7. Migration 015
requires the next minor release and its installed-upgrade checks.

The combined service, HTTP, agent-control, recovery and private-input group
passed **66 tests**, with two Windows-only private-input scenarios skipped on
Linux. After preserving the existing public-URL policy, the expanded HTTP
group passed **15 tests**. It covers configured and unconfigured loopback
HTTP without persistent cookies, IPv6, internationalized HTTPS hostnames,
origin/CSRF checks, scoped session rotation and revocation. Browser sign-in
uses the same public-address validation as MCP, so adding sign-in does not
reject previously supported localhost configurations.

All **12 TypeScript client tests** passed, including asynchronous credential
loading, a bounded timeout, and no automatic retry when the credential store
fails. All **115 Electron unit checks** passed, including the nine new
password-session tests. The native unit checks use controlled secure-store
fixtures; they do not substitute for each operating system's packaged test.
An actual Windows private-input probe separately passed owner-only reading,
hard-link refusal, the size limit and refusal of shared ACLs without repairing
them. Its foreign-owner scenario still needs an elevated native fixture.

Real browser checks used an isolated HTTPS service, a real temporary PostgreSQL
database with restricted application roles, deterministic fixture embeddings,
and synthetic people. They did not access production memory or call a cloud
model. Certificate exceptions were confined to the disposable browser context.

- A human administrator signed in, created a scoped invitation, and an isolated
  contributor accepted it and chose a password. The contributor's app omitted
  administrator navigation and retained the configured space role.
- Remembered browser credentials used Secure, HttpOnly refresh cookies with
  SameSite Strict. Browser storage held only connection metadata. A login
  without Remember retained credentials in memory and created no saved cookie.
- Reopening a remembered login rotated once. A second tab borrowed its current
  access. Two tabs continuing simultaneously produced one further rotation.
- Dropping a refresh response after the server committed it left a persisted
  pending marker. Continue became disabled, retrying did not replay the spent
  refresh token, and an explicit new login restored access.
- Changing a password revoked all three then-existing owner sessions. The
  independent owner recovery key still authenticated, and the contributor
  session remained active. The corrected app returned to that workspace's
  password form with no unauthorized follow-up requests.
- Revoking the current session returned both tabs sharing that session to
  sign-in. Ordinary sign-out did the same, retained the nonsecret workspace
  address, displayed an explanation in the other tab and removed the saved
  refresh cookie.
- At final inspection, all six owner sessions created during this browser
  exercise were revoked. The contributor still completed an authenticated
  activity request, and the independent recovery key still returned the same
  administrator. The browser contexts and disposable server then shut down
  normally, with the fixture's database cleanup completed.

The frontend production build passed with a 768 MiB process-group memory
limit, no swap and one CPU. A previous 512 MiB limit was too small for the
compiler; that build failure was an observed limit, not an application crash.

The source now identifies itself as 4.2.0, with regenerated OpenAPI and the
100-operation agent contract, matching Python/npm locks and reviewed release
notes. The release consistency check passes. The latest Electron suite passed
**120 checks** (111 ordinary checks and nine update-controller checks). New
cases verify that local startup completes before consuming a saved refresh
token, that startup failure preserves the credential, and that a different
workspace at the same local address is rejected. The native probe compiles and
its runner passes JavaScript and shell syntax checks.

The 4.2.0 preflight passed another **54 focused checks** covering local readiness,
sign-in HTTP and agent boundaries, and release-status reporting. The updated
production frontend build and Python static checks also passed. The new zxcvbn
4.5.0 dependency contains its MIT license text. Full notice generation must use
the locked build runtime: the operator's broader local test environment includes
unrelated packages and is not the packaged dependency inventory.

The installed acceptance gate now includes real invitation acceptance through
the UI, contributor-only access, protected native persistence, automatic restart
and same-session refresh, current-session revocation and independent owner-key
verification. Linux uses an isolated Secret Service keyring. These additions
still need to pass on the six native runners; compilation is not that evidence.

Remaining release acceptance includes native password sign-in and secure-store
reopening on every packaged target, the full service/client matrix, packaged
dependency notices and migration/recovery from the published installer.
Provider OAuth, company identity/SSO, remote host ownership and other full
product requirements remain separate open work.

## Retention and concurrent access follow-up

The post-checkpoint source adds periodic authentication-history cleanup. Each
batch can remove at most 2,048 retired refresh digests, 128 expired session rows
without remaining digests and 128 expired invitations. Session and invitation
metadata has a 30-day post-expiry review window. Active authority, independent
keys and audit/job anchors are retained. Database statements have a two-second
limit and overlapping API hosts use a nonblocking shared lock. The maintenance
task stops before its database pool closes.

**39 service checks passed** for retention, personal access and HTTP behavior.
Real PostgreSQL cases verify active access and private invitation preservation,
expired metadata removal, retained audit anchors, bounded digest-first deletion,
overlapping-host exclusion and denial to the worker role. HTTP lifespan checks
exercise the new task alongside ordinary sign-in and shutdown.

The TypeScript client and native bridge retry a safe request after `401` only
when their current credential differs from the rejected one. Unchanged and
revoked credentials, repeated rejection, non-idempotent writes and interrupted
credential acquisition terminate without a retry loop. **14 SDK checks and 123
Electron checks passed**, including these cases and native request deadlines.

The first full hosted service matrix on `f1ef6db` found two receipt assertions
that assumed the next globally queued job belonged to that test's tenant.
The tests now drain the real worker with a deadline and inspect their own
receipt; successful indexing is still required. The corrected full-suite run
and native validation remain pending at this checkpoint.

The full local suite was stopped by its isolated 512 MiB memory limit; the user
service and desktop were not test processes. The user journal recorded
`oom-kill`, and no pytest or private PostgreSQL process remained from that run.
The corrected focused run passed **39 checks**, including deliberately queued
earlier memories and an isolated retention-batch baseline. Full-suite validation
continues on the hosted runners.

All six first native jobs reached installation but stopped at the new probe's
Disconnect lookup: the actual control exposes its name through `aria-label`
and `title`, while the probe initially inspected text content only. The probe
now recognizes those accessible names and compiles. This is a corrected test
driver, not evidence that the remaining native sign-in phases passed.
