# Security

Report a vulnerability privately through
[GitHub's security advisory form](https://github.com/Perseusxrltd/mnemion/security/advisories/new).
Private vulnerability reporting is enabled. Include the affected version,
operating system, a minimal reproduction, expected authorization boundary, and
the impact. Use synthetic memories and test credentials. Do not put live keys,
customer content, database dumps, or private vaults in a public issue.

The [current release status](docs/RELEASE_STATUS.md) records published v4 versions
and their verified gates. The v4 series is not yet covered by a stable-release
support commitment. Historical v3 local-profile tools are retained for migration
and compatibility; they are not an authenticated shared server. The
[implementation ledger](docs/implementation/v4_progress.md) tracks source progress.

Each application needs its own key and explicit space access. Provider connectors
need explicit identity mappings; a provider bot's access is not the company's
access. Use TLS for remote services, keep database-owner credentials out of API
and worker processes, and protect local exports as copies of the data they
contain. The [deployment guide](docs/service/deployment.md) covers these boundaries
and the [recovery guide](docs/service/recovery.md) covers deletion/access-ledger
freshness and backup trust.

Review dependency alerts and pinned models before upgrades. Release verification
includes schema checks, scope/revocation tests, hostile source rendering,
recovery with later deletions, native packaging checks, dependency auditing, and
secret scanning. A successful scan is evidence for its scope, not a guarantee
that a deployment or arbitrary third-party plugin cannot be compromised.

## Release controls from 4.45.1

The 4.45.1 source adds the controls below. [Release status](docs/RELEASE_STATUS.md)
records available packages and observed gates. The dated
[4.45.0 Windows/shared-host acceptance](docs/validation/2026-10-22-4450-live-acceptance.md)
remains the record for that deployment.
Provider requests share a bounded retry/read budget, PostgreSQL recovery tools
receive a restricted environment, and HTTP/MCP/connector validation suppresses
arbitrary submitted property names. See [provider limits](docs/service/connectors.md#provider-http-and-validation-diagnostics)
and [recovery configuration](docs/service/recovery.md).

[The secret-scan wrapper](deploy/secret_scan.py) uses a free Gitleaks distribution
pinned by version and archive SHA-256, with repository-owned rules. The normal
`deploy.release_automation integrate` check scans source before public Git pushes.
Checked-in CI/release workflows scan source, generated desktop content and exact
downloaded distributions before publication. Release preflight enforces the source
scan whether Product checks are fresh or reused. Source snapshots include tracked
and unignored files.

ZIP, wheel, `tar.gz` and `tgz` contents are explicitly expanded within byte,
entry-count, nesting and time limits, then scanned as a byte stream so filenames
cannot exclude members. Binary content at the start cannot trigger an upstream
file-type shortcut. Controls must detect a synthetic application key in binary
content and application/vault keys in a nested wheel before scanning the real
inputs. Failed controls, incomplete inspection and exhausted limits prevent a
passing receipt; findings remain in
private redacted reports. Native executable internals are not decompiled, and
encrypted content is not decrypted. A passing scan covers the inspected bytes
and active rules; it does not establish that every possible secret is absent.
