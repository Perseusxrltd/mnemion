# Local database identity across Linux clock adjustments

During the 4.7.0 retention walkthrough, the source Electron harness initially
reported successful shutdown while its disposable PostgreSQL process and PID
file remained. The private engine diagnostic refused shutdown because the
database's apparent creation time had changed. The executable and data directory
still matched the original owned database.

On Linux, `psutil.Process.create_time()` combines process start ticks with an
estimated boot time. A clock adjustment in the WSL environment changed that
estimate, so an epoch timestamp comparison rejected the same process. The
existing managed-host identity helper already used Linux boot ID and start
ticks; the native database and RAM sampler had not adopted it.

## Correction and evidence

The local database now captures and verifies the shared process identity.
Shutdown still checks the bundled executable and exact data-directory argument.
RAM accounting accepts that identity and retains compatibility with existing
tuple callers. Mismatched identity makes the database measurement incomplete
and refuses shutdown.

A real bundled PostgreSQL 18/TLS test changed only the observing Python
process's boot-time estimate by 60 seconds. The OS clock itself was not changed.
The old epoch creation time moved, while RAM accounting and authorized shutdown
continued to recognize the owned process. A deliberately altered process-start
marker was refused. Restoring the correct marker allowed shutdown and removed
the PID file. The database/process-identity subset passed **19 tests**, with one
Windows-specific case skipped on Linux. The separate nine-test memory-budget
regression suite also passed.

The desktop controller now remembers unsuccessful engine shutdown. An error
diagnostic or nonzero exit cannot clear the error and report update readiness;
a successful restart and clean stop can recover. Two new checks cover these
paths. The complete desktop suite passed **159 tests**.

The real source Electron retention walkthrough was then repeated. It reported
successful stop, and an independent check found no database PID files in the
original or recovered fixture directories. The private harness now verifies
those files explicitly rather than accepting its controller result alone.

All changes and recovery actions affected disposable fixtures. The user's
Windows installation and original shared workspace were not changed. The
source fixture used a test credential cipher; installed acceptance still
requires the native release pipeline. This correction advances R02 and U05;
broader hardware and fleet requirements remain open.
