# Encrypted credentials vault — 15–19 October 2026

Source milestone: **4.12.0**. The implementation, [user/operator guide](../service/secrets-vault.md)
and [release notes](../releases/4.12.0.md) advance requirement A04 and issue 32.
The full requested roadmap remains **17/64 shipped**. Native installers and
public update acceptance are tracked separately in [release status](../RELEASE_STATUS.md).

## Focused acceptance

Final focused checks on 19 October: **55 Python checks passed**, covering the
34 vault/host checks plus existing agent-control, private sign-in and MCP
compatibility regressions. **56 desktop controller/operator checks passed**.
The TypeScript client, web Studio and Electron builds passed; both Python locks
passed offline verification. Existing OpenAPI operations and models are unchanged;
the generated contract adds the reviewed vault operations.

An additional **nine migration regression cases passed** after updating the
expected current schema. They cover upgrades from schemas 13–19, including the
published 4.11 schema, and preserve existing memory, keys, grants and password/
assistant sessions. The four new vault tables start empty. Full CI and installed
release acceptance remain tracked separately from these focused checks.

The real PostgreSQL tests exercise separate ciphertext storage, absence from
memory/search/context/Obsidian output, tenant and worker isolation, key and
signed-in-person grants, list/read/write separation, current revocation after
waiting for an administrator lock, competing writes and grants, authenticated
envelope substitution, safe errors, explicit MCP opt-in and disabled-gateway
enforcement. Export/import verifies integrity, current grants, new identities and
atomic rejection of name collisions.

An actual `pg_dump`/`pg_restore` round trip requires the separate original key,
rejects old credentials, preserves a deletion made after the snapshot and clears
old vault grants before a new administrator explicitly permits a read. Host
tests cover private configuration, bounded stdin handoffs, explicit key retrieval,
stale identity/revision refusal, damaged-file repair, external ownership and
connector exclusion of keys/recognized encrypted exports.

The private CLI acceptance also covers a near-limit value containing JSON-escaped
characters and a portable encrypted export larger than the ordinary inline result
budget. Values and exports use private input/result files; the export remains a
directly importable envelope. Existing password/key handoff regressions accompany
these changes.

Desktop controller checks cover drain/save/reopen ordering, an explicit stop
during configuration, stale settings, key/result identity checks and exclusion of
keys from public status. The actual Python operator client refuses both backup
and vault key requests without a private destination reserved before sending.

## Actual source-app walkthrough

A private browser fixture used the production `LocalWorkspace` controller, a
real PostgreSQL 18.6 database and the cached small CPU model. The browser bridge
was a restricted loopback fixture; it was not packaged Electron IPC. Synthetic
data and credentials were kept outside the repository.

Observed app behavior:

- Generated/saved a host vault key through setup and reopened the same workspace.
- Created, explicitly read, hid on blur and replaced a credential. The value was
  absent from browser local/session storage.
- Changed the current connection to write-only; its read action disappeared.
  Reinstated a read grant and verified the saved replacement.
- Downloaded an encrypted export, independently authenticated/decrypted the file,
  deleted the original credential and restored the export through the app.
- Viewed access records without values, and inspected desktop and 390-pixel
  layouts. Both credential and audit pages fit the mobile viewport.

The fixture served its web assets from the host being restarted, so its browser
reconnected after setup; packaged desktop assets are separate. A stale grant
refresh returned the expected 404 during deletion without leaving an error view.
This source walkthrough does not stand in for installed-platform acceptance.

## Native release and remaining limits

The existing six-target installed hosting gate now requires actual vault setup
and key restoration controls during its encrypted backup/recovery sequence. It
also requires missing-key refusal, fresh grant review, preserved later deletion,
absence of values from returned search hits, decrypted values after restart and
continued independent access to the original workspace. Only the normal release
pipeline can supply those platform results.

Encryption protects credential values at rest. Names and audit identifiers remain
metadata; the API host holds the key. This does not encrypt ordinary searchable
memory or plaintext Obsidian exports. Explicitly opted-in MCP reads disclose the
requested value to that client/model. Managed rotation/KMS, independent delivery
verification, KeePass and broader company controls remain open.
