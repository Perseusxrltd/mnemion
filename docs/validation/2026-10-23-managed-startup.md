# Managed service command startup

**23 October 2026.** The 4.46.0 live attempt started its API and worker but
missed the updater's complete readiness boundary and restored 4.45.1. The
[original rollout record](2026-10-23-4460-live-rollout.md) preserves that failure.
The old updater did not retain the individual failed readiness condition.

Inspection found a heavily loaded one-CPU host. An offline import profile
showed that every CLI command eagerly loaded unrelated local-workspace,
recovery, MCP and SSH setup. Version 4.46.1 defers external command options
until argparse enters that command, and loads the model registry only in the
branches that use it. Explicit module imports remain discoverable by the
native engine packager. Help, nested options and command dispatch remain
supported.

## Isolated host measurement

The [retained receipt](2026-10-23-managed-startup.json) compares the published
4.46.0 environment with two proposed source files in a private temporary
directory. Each case runs in a fresh low-priority Python process on the same
host. The worker probe stops before its database-credential boundary; an audit
hook refuses network connections, DNS resolution and listener binding.

| Command initialization | Published wall time | Proposed wall time | Published CPU time | Proposed CPU time |
| --- | ---: | ---: | ---: | ---: |
| Top-level help | 9.51 s | 0.26 s | 4.64 s | 0.10 s |
| Worker before database access | 9.91 s | 1.92 s | 4.90 s | 0.95 s |

The worker case loaded 1,033 modules before the change and 461 afterwards;
the proposed case loaded neither MCP nor AsyncSSH. Worker command CPU time
fell about 81%. Each entry is one observation under changing host load.
This measures startup work only and does not establish total initialization,
retrieval performance or successful production cutover.

The probe changed no installed files, opened no database/network connections,
made no service requests and removed its temporary files. The receipt binds
the compared source files and probe program by SHA-256.

## Readiness and recovery regression checks

The focused CLI and managed-update suite passed **59 checks**. These cover
basic help without loading model/client/recovery stacks, all deferred command
option sets, native host schema dispatch, signed update and compatibility
guards, backup before cutover, runtime rollback without reverting accepted
data, interrupted-update recovery, and holding failed versions.

Running children still cannot bypass failed HTTP, process-identity or
initialization checks. Their simulated transitions retain the existing
60-second deadline. Timeout evidence records only known reason/state values
and boolean readiness fields; arbitrary settings and error text are excluded.

The change retains this bounded evidence in the journal before recovery and
in the failed-attempt record after rollback. A diagnostics-write failure does
not prevent attempting the original runtime rollback. `updates status` exposes
the preserved evidence; older failure records return no invented detail.

Full source/native publication gates and renewed actual Windows/shared-host
acceptance are pending at this source checkpoint. Controller OS adoption,
fresh independently verified backup and both custodians' recovery journey
remain separate requirements.
