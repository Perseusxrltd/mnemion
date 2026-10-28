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

## Installer work and remaining acceptance

The same source replaces uncompressed desktop packaging with balanced lossless
compression and extends the existing installer verifier with component-size
reporting. Source parsing, effective builder configuration and release validation
passed. Actual compressed size, signed updates, installation and recovery require
the normal native matrix. See the [measured baseline](../implementation/installer-footprint.md).

Issues 44, 47 and 48 remain open. The reporter's four-session search failures,
source freshness, all eleven-space acceptance, native task workflow and complete
vault format/sync criteria remain tracked. All 66 requirements are retained.
V08 stays Building, with production telemetry collection disabled and its full
privacy/resource/platform acceptance and completion notification still pending.
