# Managed startup and release diagnostics — 14 October 2026

The first frozen 4.2.5 release attempt was not published. Its managed-service
checks on both native Macs timed out while the API was healthy and both processes
were running. Focused run [38570372830](https://github.com/Perseusxrltd/mnemion/actions/runs/38570372830)
captured the worker's stack inside `HTTPServer` construction, before publishing
the broker address or worker readiness record. All six standalone pinned-TLS
broker checks had passed. The local listener now binds its numeric loopback
address directly and skips `HTTPServer`'s unnecessary reverse DNS lookup.

The regression check makes reverse DNS unavailable and completes a real pinned
TLS query. It and the other broker checks plus the real API/worker crash/restart
scenario passed together: **8 checks, 19.88 seconds**, on Linux under a 768 MiB
memory limit. Native Mac acceptance remains part of the immutable release gates;
these local results alone do not claim a native platform pass. The change does
not alter the model, vectors, or pipeline fingerprint measured in the
[shared-model comparison](2026-10-14-shared-model-runtime.md).

The first release's synthetic Windows x64 NSIS replacement also timed out after
the verified installer launched and the old application exited. The focused
[Windows run 38568607776](https://github.com/Perseusxrltd/mnemion/actions/runs/38568607776)
passed installation, local workspace use, signed-update rejection cases,
restart guards, replacement and relaunch with the same production installer and
controller behavior. No cause is asserted for the earlier timeout. Failure
capture now includes only the disposable installer's process tree and dialogs,
plus free disk space, to make any recurrence diagnosable.

Managed fixture diagnostics now report readiness comparisons and bounded code
locations automatically. Temporary Python stack hooks apply to the disposable
non-isolated bootstrap only; they do not weaken isolated runtime installation.
No passwords, tokens, exception messages or private paths enter the summarized
managed diagnostics. The ordinary Supervisor error handler also retains safe
diagnostic categories, OS error numbers and Mnemion code locations.

The maintenance board now retains a next-version failure that finishes after an
older version publishes, even if it started earlier. Active builds are inspected
for already-failed jobs. Completed unchanged failures reuse their saved job
evidence. Version and publication-specific results continue to be recorded by
the [release-status workflow](../RELEASE_STATUS.md).
