# Security

Report a vulnerability privately through
[GitHub's security advisory form](https://github.com/Perseusxrltd/mnemion/security/advisories/new).
Private vulnerability reporting is enabled. Include the affected version,
operating system, a minimal reproduction, expected authorization boundary, and
the impact. Use synthetic memories and test credentials. Do not put live keys,
customer content, database dumps, or private vaults in a public issue.

The v4 branch is in release validation. It is not yet covered by a stable-release
support commitment. Historical v3 local-profile tools are retained for migration
and compatibility; they are not an authenticated shared server. Track current
support and release gates in the [implementation ledger](docs/implementation/v4_progress.md).

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
