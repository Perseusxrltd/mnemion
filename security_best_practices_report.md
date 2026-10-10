# Mnemion security review — 10 October 2026

The rebuild addresses high-priority file-access, recovery, authorization and
request-handling risks. One moderate advisory remains in the desktop build
toolchain; its reachable behavior and distribution scope are documented below.
The product remains in release validation. This report does not certify every
provider account, operating system, third-party plugin, or deployment.

The review covers the current `codex/mnemion-v4` working tree: Python/FastAPI
service, database policies, source adapters, backup/restore, Obsidian export,
React Studio, and the Electron bridge/build configuration. References use the
current source lines; the final release must retain the exact source, lockfiles,
test outputs and artifact hashes used for its checks.

## Fixed high-priority findings

### 1. Selected-folder check/open race

An attacker able to change a selected source tree could replace a checked path
before it was read, potentially importing a file outside that tree. The reader
now opens through anchored directory descriptors with `O_NOFOLLOW` on POSIX, or
checks the actual Windows handle path before reading bytes. It also rejects
non-regular files and content changed during capture.

Evidence: [source reader](mnemion/connectors/source_files.py#L36), selected-folder
race/permission tests in `client_tests/`, and bounded provider tests. Native
Windows checks passed in the earlier session; the final current native matrix
must be rerun. Original transient proof logs were lost in the WSL restart and
are not presented as retained release artifacts.

### 2. Unbounded incomplete request lifetime

The prior body-size limit did not expire a slowly delivered incomplete body,
allowing clients to hold the service's finite request capacity. Per-chunk list
storage also added overhead unrelated to the byte limit. The middleware now
rejects excessive or ambiguous declared lengths before reading, uses one bounded
buffer, and expires body reception after 30 seconds with a sanitized 408 error.

Evidence: [request boundary](mnemion/service/api.py#L46) and
[transport tests](service_tests/test_request_limits.py). The focused HTTP,
transport and hostile-export group passed eight tests on 10 October. A TLS proxy
still needs deployment-specific connection/rate limits; this fix does not claim
protection against every distributed denial-of-service workload.

### 3. Untrusted evidence could activate exported markup

Memory/source content may contain HTML images, code fences or template delimiters.
Treating it as generated Markdown can turn evidence into active markup in a
visualization tool. Generated evidence now uses escaped literal text; titles and
labels are escaped, and YAML preserves parsed values while encoding raw `<`
characters that could begin a template directive. Canonical source bytes remain
available separately through authenticated source/attachment APIs.

Evidence: [safe rendering](mnemion/service/markdown.py#L15),
[frontmatter serialization](mnemion/service/markdown.py#L38), and
[hostile markup tests](service_tests/test_export_markup.py). Native Obsidian
rendering of the final format remains an acceptance gate. Installing an arbitrary
plugin can give that plugin broader access; this protection is not a plugin sandbox.

### 4. Recovery could reinstate obsolete access or use stale credentials

Restoring only positive data can reintroduce deleted memories or revoked grants.
Service recovery requires a later independent denial/access ledger, verifies
table hashes, removes denied data, rotates API keys and suspends provider scopes
until permissions are re-observed. Explicit deployment activation checks the
new administrator key and matching recovery record before publishing one atomic
database/owner selection. Interrupted publication can be resumed without
bootstrapping another organization or overwriting the original database.

Evidence: `service_tests/test_recovery.py`, connector recovery/denial tests, and
[restore activation](mnemion/service/deployment.py#L250). The focused
recovery/setup/evaluation group passed ten tests with one Windows-only skip,
including a real restore, stale-key rejection and interruption after activation
commit. Ledger freshness limits how recent a lost deletion/revocation can be
reconciled; the [runbook](docs/service/recovery.md) states that boundary.

## Open moderate advisory and disposition

### 5. `sprintf-js` unbounded precision in the desktop build dependency tree

The 10 October npm audit reports eight moderately affected packages, zero high,
and zero critical findings. They share
[GHSA-hp3w-g68c-fv3c](https://github.com/advisories/GHSA-hp3w-g68c-fv3c):
`sprintf-js` through `roarr`, optional `global-agent`, `@electron/get`, and
`electron-builder`. The vulnerable behavior requires a format string containing
unbounded precision. The reviewed `global-agent` logger call sites use static
format strings and place variable values in structured context.

These dependencies build/download Electron; they are development dependencies
and are not included as application JavaScript by the package's `dist/**` file
selection. Electron itself and its bundled Chromium components remain separate
runtime dependencies with their own notices and update requirements.

Disposition: retained with documented build-only exposure pending an upstream
fix. Do not downgrade the current builder to npm's suggested older builder solely
to hide this audit result. Recheck the dependency path and actual packaged ASAR
before release and on every update. The advisory remains open; the audit is not
described as vulnerability-free.

## Controls reviewed and deployment boundaries

- Database startup rejects owner, superuser, RLS-bypass and mixed API/worker
  logins. Transactions recheck key revocation and set tenant/principal scope
  locally: [database boundary](mnemion/service/db.py#L91).
- Retrieval, sources, revisions, context, graph/wiki, exports and workers use
  current authorization and lifecycle checks. Organization administration alone
  does not grant access to every memory space. Cross-tenant, revoked-grant,
  quarantine, concurrent-correction and deletion cases have dedicated tests.
- Provider permissions expire and unmapped identities receive no access.
  Git/rclone/folder publication requires explicit mapped recipients. Provider
  tokens stay with the adapter. Live customer-provider OAuth/ACL acceptance has
  not been performed.
- API errors avoid echoing source text or credentials. Remote deployments require
  TLS; desktop connection setup rejects non-loopback plaintext addresses. Browser
  keys remain in window memory. Electron uses a sandboxed renderer, isolated
  preload, constrained methods/headers, response bounds and no redirect following.
- Local setup files use private POSIX permissions or an explicit Windows DACL:
  [setup directory handling](deploy/manage.py#L27). API and worker containers
  receive separate derived credentials, never the database-owner password.
- Source command output is bounded while a process runs, and timeouts terminate
  its process group. Source text never chooses a shell command.
- Deletion denies subsequent service reads immediately; purge is asynchronous.
  Previously downloaded exports, host backups and third-party copies have their
  own retention boundaries. A checksum detects corruption but does not make an
  attacker-controlled backup trustworthy.

## Publication and release checks

The current production Python audit found no known advisories in its 58
third-party distributions; the local Mnemion distribution is not a PyPI advisory
target. Desktop build advisories are described separately above. Dependencies,
native subcomponents and platform behavior must be assessed together with the
actual release artifacts.

License collection now inventories runtime Python distributions, selected frozen
desktop components and npm production packages, copies available upstream notices,
and emits CycloneDX package inventories. Missing wheel licenses have exact-version
copies from verified source artifacts/commits. This is package-level inventory;
review bundled native notices and final artifact contents before distribution.

GitHub private vulnerability reporting is enabled, with a public reporting guide
in [SECURITY.md](SECURITY.md). Current worktree/history secret scans, the full
regression matrix, native packaging and Obsidian acceptance, final artifact
inspection, and Windows/Apple signing remain release gates. No unsigned build is
presented as a signed public release, and no public release has been published.
