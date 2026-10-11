# Windows private state validation — 2026-10-11

## Failure and change

Elevated Windows runners created Administrators-owned workspace directories.
The previous owner-rights ACL then depended on a group that PostgreSQL removes
when `initdb` creates its restricted token. Desktop state/RAM tests rejected the
same directories because their owner differed from TokenUser.

Commit `d664e91` creates directories and exclusive files with Win32 security
attributes that explicitly name TokenUser as owner and sole allowed SID. The
protected directory DACL carries object/container inheritance for engine-created
children. Existing directories still require matching ownership; opened handles
are also checked for directory and reparse attributes before applying a DACL.
The native PostgreSQL probe uses the same production private-directory and
secret-output helpers. PostgreSQL's token restriction remains enabled.

Commit `08c60c1` makes the native assertions inspect binary SIDs and ACEs because
Windows renders the CI account SID as the SDDL alias `LA`. The foreign-owner
fixture uses the Win32 API directly, avoiding PowerShell module-version mixing.

## Evidence

[Native database run 38128713835](https://github.com/Perseusxrltd/mnemion/actions/runs/38128713835),
head `08c60c1f9404d4c612b1a4bc315bb59a75092a8d`:

- [Windows x64 private state](https://github.com/Perseusxrltd/mnemion/actions/runs/38128713835/job/114438387196): 10 passed, 2 POSIX-only skips.
- [Windows ARM64 private state](https://github.com/Perseusxrltd/mnemion/actions/runs/38128713835/job/114438387374): 10 passed, 2 POSIX-only skips.

These jobs verify current-user ownership, a protected single-user ACL, inherited
privacy, durable state and RAM settings, interprocess lock behavior, preservation
of an existing foreign-owned folder, and rejection of redirected parents.
The elevated foreign-owner fixture ran on both CI architectures.

The access regression calls `CreateRestrictedToken` with `DISABLE_MAX_PRIVILEGE`
and Administrators/Power Users disabled. It verifies that any such groups in the
original token become deny-only and cannot grant access. While impersonating the
restricted token, it opens inherited and explicit files for read and execution,
reads their bytes, lists/traverses the workspace, and creates/reads/deletes a new
child. Both Windows jobs must pass before any database builder starts.

Local validation also passed: Windows Python 3.13 had 7 passes and 3 expected
skips (two POSIX tests and the elevated-only fixture on a normal user session);
Linux state/archive regressions had 15 passes and 4 Windows-only skips. Ruff and
workflow parsing passed. The combined branch's nine native retrieval/readiness
integration cases passed against a disposable PostgreSQL instance under a 1 GiB
memory bound.

## Follow-up native probe corrections

Both Linux database jobs passed the complete relocated probe. Both Mac builds
completed, then the stricter production directory check exposed the system
`/var` symlink used by the temporary directory. The probe now canonicalizes only
the OS temporary parent before creating its private root. A POSIX regression
reproduced the original failure through a temporary symlink and passed after the
correction; user workspace paths still reject redirected parents.

The Windows build completed and `initdb` succeeded. Its next `pg_ctl start` call
hit a different Windows issue: a server descendant inherited the subprocess
output pipes, so `subprocess.run` timed out after 60 seconds and then waited
indefinitely in its own `process.communicate()` cleanup. The disposable CI run
was canceled after the probe remained stalled for over seven minutes; the
[completed job traceback](https://github.com/Perseusxrltd/mnemion/actions/runs/38128713835/job/114438496054)
identifies that exact stack. This was not another directory access failure.

`private_process` now captures native-tool output in exclusive user-owned regular
files with Windows delete sharing, returning at launcher exit without waiting
for descendant pipe EOF. Captured reads are limited to 4 MiB per stream. The
helper preserves closed private stdin and no-console Windows launching. Real
process regressions cover a still-running descendant retaining output handles,
timeout cleanup, and the output limit; all pass on native Windows. The native
probe uses this helper, precreates/rechecks its private data folder like
production, and emits tool names to locate stages without printing credentials
or command arguments. The corrected full Linux database probe passes locally.

## Follow-up Unicode path correction

[Native run 38130421406](https://github.com/Perseusxrltd/mnemion/actions/runs/38130421406),
head `5c0ac681d5d0d5bc0dc5dfccdfa2699d64e63178`, passed all four Unix
database probes. Both elevated Windows private-state jobs passed 13 tests with
3 POSIX-only skips. The Windows database initialized and started promptly,
confirming the process-capture correction, then failed its strict data-directory
identity check. TLS verification and data checksums were both correct.

A local native-Windows reproduction against the retained CI archive showed
PostgreSQL reporting `Workspace data quipe` for `Workspace data Équipe`.
PostgreSQL's Windows tools use narrow command-line arguments and filesystem
calls; their processes therefore need a UTF-8 active code page to preserve this
identity. The probe keeps its Unicode directory and exact identity comparison.

The builder now merges a UTF-8 active-code-page application manifest into every
packaged executable before hashing and packaging. Existing identities, trust
settings and dependencies must survive the merge, and the actual embedded
resource must match the verified XML. Executables without an identity receive
one with their actual PE architecture; DLLs retain the host process's settings.
The Windows runtime requires Windows 10 version 1903 (build 18362) or later,
including Windows 11, which implements this manifest setting.

Using Windows SDK 10.0.26100.0 against the retained CI archive, all 42 executable
manifests embedded and verified. A separate copy of native Python 3.13 also
passed the existing-manifest preservation check. After recomputing the archive
inventory, the complete native Windows probe passed locally with both
executable and data paths accented: exact directory identity, verified TLS,
checksums, vector search, RLS read/write isolation, gzip backup restore, and
immediate-shutdown recovery. The production builder still needs its rebuilt CI
matrix, especially the Windows ARM64 emulation gate.

[Product run 38130421330](https://github.com/Perseusxrltd/mnemion/actions/runs/38130421330)
passed all 11 jobs at the same head, including both Docker architectures,
Python 3.12/3.13/3.14 service suites, and both Mac supervision jobs.

## Remaining gate

The rebuilt database matrix and Windows ARM64 emulation must pass with the
manifest fix; the retained-archive experiment does not replace those build gates.
Passing the ACL checks does not establish complete app installation,
model/service onboarding, or signed Windows distribution readiness.
