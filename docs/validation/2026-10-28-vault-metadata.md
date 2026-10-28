# Exact-key vault metadata and installer compression

Source: **4.46.46**, reviewed 28 October 2026. This is source qualification;
native publication and actual shared-host/client acceptance remain separate.

## Behavior verified

The new migration adds exact-key metadata auditors. Current tenant, principal,
key retirement and grant expiry are checked without adding value permissions.
MCP metadata exposure has an explicit host setting independent of secret-value
tools. App, Python/TypeScript SDKs and the agent catalog expose grant inspection,
versioned changes, expiry and revocation. Old host files and omitted settings
retain their earlier behavior.

- **49 distinct Python cases passed** across the new metadata suite, existing
  vault and local setup suites, and the generated agent contract check. This
  includes real PostgreSQL permissions, competing grants, expired/revoked keys,
  disabled owners, cross-tenant refusal, missing-key repair, worker exclusion,
  full/compact HTTP MCP and an actual database backup/restore that disables
  historical auditors and retains their incremented revisions.
- **22 TypeScript SDK tests** and **70 desktop control tests** passed. The
  frontend and desktop source builds passed. These are not six-platform
  installed-package results.
- **One real browser/app journey passed** against a fresh PostgreSQL/API and
  the built Studio frontend in headless Chromium. An administrator granted an
  expiring auditor role; that agent, without memory-space grants, reached
  Secrets and its audit log without value or grant-management controls.
  Returning to the administrator and revoking the role persisted revision 2,
  removed the agent's listing access and preserved the original credential.
  This was synthetic data only, with no production vault reads or writes.

## Retained failures and corrections

The initial Python run had 46 passes and three assertion failures. Two old
assertions required all metadata to close when the encryption key was missing
or invalid; they now verify the intended metadata repair path while explicit
value reads remain closed. One new assertion expected an empty second-tenant
audit after deliberately making denied requests; it now verifies that only that
tenant's own attempts appear. Four targeted cases then passed, including the
updated disabled-host control. Runtime behavior was not changed to pass them.

The first interactive browser fixture expired before its review finished. Its
replacement automated run stopped on a test selector: an input with a datalist
has the `combobox` role, not `textbox`. Correcting that selector produced the
successful complete journey. Both earlier records are retained; neither is
presented as a successful app review.

The first full source CI run caught two missing origin-map declarations for
the newly added vault controls. The follow-up maps explicit auditor changes
to the existing access workflow and excludes automatic auditor-list queries
from usage counts. Its 16 Python origin/coverage checks and 24 Studio measurement
checks passed. The generated coverage view was refreshed; no collection setting
or telemetry release qualification changed. The original failed CI is retained.

The next full source run caught a migration regression: replacing the vault
audit constraint had omitted the three existing KeePass actions. The correction
retains preview/import/export history and updates the exhaustive upgrade
inventory for the new table and nullable audit-target column. **50 focused
PostgreSQL cases passed**, covering 15 preceding schema versions, existing
KeePass histories, current import/export and metadata-auditor permissions. The
original failed run is retained; native qualification uses the corrected source.

That source passed [Product checks](https://github.com/Perseusxrltd/mnemion/actions/runs/40751361702).
The ensuing [native run](https://github.com/Perseusxrltd/mnemion/actions/runs/40757944923)
passed Linux x64/ARM64, Windows ARM64 and Mac Apple Silicon. Two failures remain
recorded: Windows x64 exceeded a 20-second Python fixture deadline while filling
a synthetic telemetry quota, and Intel Mac reported unreadable local settings
when reopening a recovered workspace. Neither failed platform is accepted.

The follow-up reproduced a real local-state race: an atomic settings replacement
between path inspection and opening the file, or immediately after opening,
could incorrectly report damaged state. Both timing cases failed on the
original source. The reader now reopens and validates the current private file
up to three times. A continuously changing writer returns a distinct retryable
error; linked, oversized and actually damaged records remain protected and
their bytes are retained. **42 focused Python cases passed, with four platform
skips**, covering these regressions and local readiness, recovery, backup and
vault behavior. The Intel Mac incident has the same outward error; the original
runner evidence does not prove that this race caused it. Its native recovery
check must confirm the corrected behavior.

Only the Windows fixture's repeated quota setup gets a 60-second deadline;
ordinary fixture operations retain 20 seconds, and product resource and hot-path
assertions are unchanged. The Electron build and targeted denied-burst test
passed locally. An initial mistyped Python test path ran no tests and is retained
separately from the corrected successful run. Windows native confirmation and
the remaining release gates are pending.

## Installer work and remaining acceptance

The same source replaces uncompressed desktop packaging with balanced lossless
compression and extends the existing installer verifier with component-size
reporting. Source parsing, effective builder configuration and release validation
passed. The resulting Mac disk images measure **263.5 MB on Apple Silicon** and
**271.0 MB on Intel**, approximately 60% below the public 4.46.44 images.
They remain unpublished; complete signed update, installation and recovery
qualification requires the corrected native matrix. See the
[artifact measurements](../implementation/installer-footprint.md).

Issues 44, 47 and 48 remain open. The reporter's four-session search failures,
source freshness, all eleven-space acceptance, native task workflow and complete
vault format/sync criteria remain tracked. All 66 requirements are retained.
V08 stays Building, with production telemetry collection disabled and its full
privacy/resource/platform acceptance and completion notification still pending.
