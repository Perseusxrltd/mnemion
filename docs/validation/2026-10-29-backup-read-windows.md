# Backup reader qualification on Windows

Recorded 29 October 2026. This corrects a platform assumption in the new
regression fixtures; the application runtime is unchanged.

A real Windows Node 25.2.1 probe returned `EPERM` when replacing a file whose
reader was still open. The new POSIX fixtures had attempted that operation
before returning the open descriptor, so they could not model Windows'
sharing-lock behavior. The application already uses bounded atomic-replacement
retries for that lock.

Replacement before opening remains a shared regression case. Replacement
after opening and during a read now run on POSIX. A separate real Windows case
starts the replacement while the reader holds its descriptor, observes the
sharing refusal, verifies a consistent first read, then verifies that replacement
completes after the reader closes and the next read sees the new revision.

| Environment | Corrected backup and atomic-write suites |
| --- | --- |
| Windows, Node 25.2.1 | 31 passed, zero failed, four POSIX-only cases skipped |
| Linux, Node 22.22.0 | 33 passed, zero failed, two actual-Windows-only cases skipped |

The Windows run also passed the existing native check that holds a file without
delete sharing. It used disposable local files and the same compiled runtime
as the original 4.46.51 source. The temporary fixture was removed after success.
These checks do not replace the packaged Electron and installed-app gates.

| Retained evidence | SHA-256 |
| --- | --- |
| Unchanged reader TypeScript | `895578b0120410c6da96ef336e26a46024d38d41dbb0e08e15497dbd1affcccb` |
| Corrected backup tests | `20b8b1d3cd0200f4926d256ec09ea25f14b791b3725057b06c6e82be503446f7` |
| Windows focused-suite log | `d4ad66ce640c8af923a2e9dc8e9bec7c2bcf79abf453a31ce9fc605484a1963d` |
| Linux focused-suite log | `6993869989ccb3d25fc95833ace7c7ffd02ca950f2bffbcb5e9f900c04179f03` |

The [original Linux installed failure](2026-10-29-backup-read-snapshot.md)
remains retained with its exact cause unconfirmed. The original 4.46.51 native
candidate is separate from this correction; no failed or running qualification
is relabeled as passing. Release publication and the full native matrix remain
required. The 66 requirement states and V08's disabled collection are unchanged.
