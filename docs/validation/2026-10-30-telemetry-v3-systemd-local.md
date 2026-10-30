# Local v3 collector under systemd

30 October 2026, 04:54:21–04:54:39 UTC. One isolated WSL systemd fixture passed
against source `11ffe6b07fc15a6aab245405e42649f9c93a0e96`. This qualifies the
operated local unit only. Production collection remains off; no public listener,
canonical memory service, VPS or user workspace was changed.

The fixture started only its loopback socket. A real TLS 1.3 request activated
the service and its valid 25-byte v3 body received HTTP 204. A valid four-byte
legacy report received HTTP 404. The private v3 store and quiet service journal
checks passed. Cleanup removed the owned units, account, group, runtime and
state, and released the port.

The unprivileged service had no effective capabilities, no-new-privileges and
seccomp enabled. Actual outbound connect and bind attempts were denied. Its
loaded credential was readable by the service and root, read-only, and denied
to an unrelated user. File mode `0440` and directory mode `0550` were explained
by ACL masks: only root and the named service user had effective access; groups
and other users had none. No credential contents enter the retained report.

The shipped unit's hardening remained in use. Its operated cgroup had a
128 MiB memory limit, no swap, 25% of one CPU core, and 16 tasks. These are
configured collector limits, not measured app telemetry overhead or acceptance
of the separate 8 MiB / 0.5% app budgets. The fixture used `Restart=no` and a
120-second maximum lifetime, rather than exercising operational restart.

The first attempt at 04:39 failed before accepting a report because the
verification predicate rejected all group-class mode bits without interpreting
the ACL. It did not retain the original credential metadata, so its exact mode
cannot be recovered. That attempt also hit a cleanup error after `userdel`
removed the empty primary group. Its failure and subsequent cleanup completion
are preserved. The corrected attempt validates the actual ACL/access rules and
removes the group only if it still exists; no hardening was relaxed.

Private evidence is retained in the original
`2026-10-30-telemetry-v3-local-systemd` and corrected
`2026-10-30-telemetry-v3-local-systemd-r2` proof directories. The unchanged source
archive SHA256 is
`114754af422870c11f577d49b6429d69d17481a4764b45c9625544ed451ebb6f`.
The corrected script SHA256 is
`f3f1c361102405d8510ea8b0b348c34bf69d8aaac21bc1f14db778b7e64dba13`.

Public-host deployment, provider privacy, installed/browser delivery, resource
acceptance and useful fleet statistics remain unqualified by this local check.
