# Windows backup file metadata correction

The second 4.5.0 installed release attempt reported **“The backup input changed
or exceeds the supported size”** on both Windows x64 and ARM64. The error became
visible after the backup alert and acceptance diagnostics were corrected. The
candidate was not published; its backup/recovery features and this correction
are included in the 4.6.0 source.

On the actual Windows computer, Python 3.13.11 returned identical device, inode,
size and modification time through `Path.lstat()` and `os.fstat()`, but different
`st_ctime_ns` values. The path observation reported creation time; the handle
observation reported change time. Requiring those different observations to
match rejected an ordinary unmodified input before cryptographic processing.

The corrected cross-open comparison still checks device, inode, byte count and
modification time on Windows. Other platforms retain the full comparison.
After reading, all platforms compare the full handle metadata, including change
time, with the original handle observation. Streaming limits, regular-file and
redirected-file checks, complete GCM authentication, verified digests and
exclusive output publication remain in place.

## Evidence

- The actual Windows encryption roundtrip failed with the original source and
  exactly the installed error, using a disposable file and key.
- The same native Windows run passed both tests after the correction:
  encryption/verification/decryption of a multi-chunk file with non-ASCII paths,
  and refusal of a file modified during its open read.
- The combined encryption regression and new native metadata checks passed
  **26 tests on Linux**. The complete native installed pipeline remains required.
- Both Windows hosts now run the two metadata checks before their service engine
  and installer work, with the project's pinned cryptography version and the
  same x64 service interpreter used by both packages. The check leaves the
  unchanged native database compiler cache usable.
  This detects the defect without waiting for a complete installer build.

Only disposable local files were used. The installed Windows app, production
workspace and user backups were not modified by the reproduction. Consult
[release status](../RELEASE_STATUS.md) for published artifacts and native gates;
these focused results do not themselves establish an installed release pass.
