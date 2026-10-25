# Windows telemetry test-helper lifecycle

**Source checkpoint, 25 October 2026, 22:57 UTC.** Focused Linux and Windows
component checks passed for the [4.46.9 candidate](../releases/4.46.9.md).
Its native release was not yet dispatched; public and installed 4.46.6 remain
the last verified baseline. See [current release availability](../RELEASE_STATUS.md).

## Preserved release failure

In the frozen [4.46.8 workflow](https://github.com/Perseusxrltd/mnemion/actions/runs/40236329055),
[Windows x64 job 121300301931](https://github.com/Perseusxrltd/mnemion/actions/runs/40236329055/job/121300301931)
failed tests 249 and 250 at **21:47:16–17 UTC**: the readiness assertion
`/^ready\n/` rejected Python's Windows output `'ready\r\n'`. Waiting helpers
remained alive after the assertions, leaving npm open until the job timed out
and finished cancelled at **22:44:46 UTC**. The failure scope was test-helper
coordination; it establishes no installed Windows app-runtime regression.

Cancellation of the unpublishable workflow was requested at **22:55:11 UTC**.
Windows ARM job 121300301890 finished cancelled at **22:56:04 UTC**, followed by
the workflow at **22:56:05 UTC**. Original Linux/macOS job successes and the
failed Windows log remain retained; they do not establish all-six qualification
for 4.46.8. The earlier [native build portability correction](2026-10-25-native-build-portability.md)
is preserved separately.

## Source correction and focused checks

The shared [fixture helper](../../studio/electron/scripts/telemetry-fixture-children.mjs)
assembles split readiness records, accepts LF/CRLF, limits readiness to five
seconds and 64 characters, and bounds helper execution to twenty seconds.
Cleanup kills any remaining helper, awaits its close with a five-second bound,
then permits fixture removal. Both [delivery tests](../../studio/electron/scripts/test-telemetry-delivery.mjs)
and [store tests](../../studio/electron/scripts/test-telemetry-store.mjs) use it.
A real-helper regression checks fragmented CRLF and complete cleanup after
readiness rejection. The [source CI](../../.github/workflows/ci.yml) and
[native workflow](../../.github/workflows/desktop.yml) give the desktop npm
test step a ten-minute bound without removing or skipping checks.

| Focused selection | Result | Duration |
| --- | --- | --- |
| Linux, Node 22.22.0 | 29 passed, 2 Windows-only skips; 31 total | 14.3527 s |
| Actual Windows, Node 25.2.1 / Python 3.13.11, corrected process wrapper | 31 passed, no failures or skips; exit 0 | 25.6881 s |

The first Windows run reported **31 passed, no skips in 26.8246 s**, but its
PowerShell `Start-Process` wrapper returned a null exit code. That failed
wrapper receipt remains preserved despite the passing test output. The
separate corrected run used `Diagnostics.Process`, finished at
**22:57:17.804 UTC**, and verified exit 0 plus temporary-fixture cleanup. Its
receipt records 116 input hashes; the three changed helper/test files match
the reviewed source. These are Node/Python native component checks, not
installed Electron or complete telemetry qualification.

## Evidence and limits

Private originals remain retained; only their hashes and public source/run
links are recorded here.

| Original evidence | SHA-256 |
| --- | --- |
| Windows x64 release log | `f96bad4280b0549d41ae060c731aecfb8910e37cdef20a4c971d14f206b367db` |
| Linux focused log | `9cfb36f45bb62158d28cf1a76f750b535e3391678207206859dd1dbea850fa76` |
| First Windows wrapper receipt | `dbf758901607a9de407d11ffc884ec8dcb46f1f96af78d239512fadba633b1be` |
| First Windows test output | `370240bc8af829bf25890f382c3be2cae96a9e3166c991d5fe596640d3dc3197` |
| Corrected Windows receipt | `0b6a5637c5abebedadaa0bf2de5bea16f03a7c528269e3da7319dc327055951d` |
| Corrected Windows test output | `21707c779b0e55c54f523cb8fa16a394f06907f8e6b7fea7b0b12f6b96cfccbc` |
| Shared fixture helper | `add67e7bb41a0836f44e5176e93e2dfafe8c95d2a0a3383fb52515f199de5bad` |

All-six-native, publication, public upgrades and actual installed 4.46.9
acceptance remain pending. The retained backup-capture correction still needs
installed acceptance. All 66 requirement texts/states are unchanged; V08
remains Building, with production collection/destination/route false/null/null.
Full telemetry resource, platform and collector/ingress privacy qualification
remain open. The separate [finite collector staging check](2026-10-25-telemetry-collector-service.md)
does not activate production collection.
