# Backup metadata snapshots during atomic replacement

Recorded 29 October 2026. Local source qualification; installed platform
acceptance remains pending.

The 4.46.50 Linux x64
[installed local-hosting job](https://github.com/Perseusxrltd/mnemion/actions/runs/40815491489/job/123273331148)
failed during `backup-resume` with `local:backup-status` and the fixed public
message: “Backup settings could not be read safely. Existing recovery files
were retained.” Earlier local create/resume, backup capture and backup recovery
phases passed. The original job log and failure artifact are retained. The
runner's detailed private file diagnostics were unavailable, so the exact
cause of that failure is **not established**.

Separate real-filesystem regressions reproduced a reader defect: a valid
atomic replacement between `lstat` and `open` caused a safety error, and a
replacement after opening or during reading could return the old, unlinked
document. The original reader also did not recheck the opened descriptor's
permissions and could expose a native open error containing a file path.

The corrected reader permits at most **two opens**. It independently checks
each descriptor's file type, link count, ownership, permissions and 256 KiB
size limit. A replaced inode or an unlinked descriptor permits one fresh
attempt. Metadata is checked again after reading. In-place changes, invalid
JSON, unsafe files and repeated replacement fail with the same fixed public
message. Descriptors close before another attempt. The read never writes,
deletes or resets backup data.

| Qualification | Observed result |
| --- | --- |
| Original implementation, eight new cases | Two passed, six failed, zero skipped |
| Corrected backup and atomic-write suites | 33 passed, zero failed, one native-Windows-only skip |
| Replacement before open, after open and during read | New document returned after exactly two opens |
| Two consecutive replacements | Read refused after two opens; latest file retained |
| Permissions widened after initial path check | Refused after one open |
| In-place size change or corrupt JSON | Refused without another open |
| Symlink substituted after path check | Fixed public error; no path disclosed |
| TypeScript compilation | Passed |

The tests ran on native Linux Node **22.22.0**. The skipped existing check
requires an actual Windows reader denying delete sharing. Simulated Windows
atomic-write, cancellation and protected-key checks passed; those are not a
substitute for installed Windows qualification. The normal native release
matrix remains required for this candidate.

Private retained receipts are bound below; no recovery keys, personal paths or
memory payloads are included in this report.

| Retained evidence | SHA-256 |
| --- | --- |
| Corrected reader source | `895578b0120410c6da96ef336e26a46024d38d41dbb0e08e15497dbd1affcccb` |
| Backup test source | `a8644545826329dca6c8ecd1da2e9105ae2b77c4c2f00aedd7e8e3830e79c730` |
| Corrected focused-suite log | `ff7b3df6e81558d10cb97eef4259b6ea15eca69e27ad46f4647430eeb239d9cf` |
| Original installed failure artifact JSON | `3d979843edbd928af5337ff039680727777cf16b1e919f94a671254789e244c4` |
| Original installed job log | `183b9a6ed5d8a566af0d81263f1c144edca366b9786cd9d718cdbce1507829c6` |

Public **4.46.49** remains the verified distribution at this checkpoint.
[Shared-host backup delivery](2026-10-29-backup-pack-index-repair.md), issues
44/47/48 and full telemetry acceptance remain open. The original 66 requirement
states are unchanged; V08 is Building with collection disabled.
