# Native telemetry deadline observation

**Source checkpoint, 25 October 2026.** The [4.46.10 candidate](../releases/4.46.10.md)
corrects a native transport test's observation boundary. Production transport
code and the five-second reservation lifetime are unchanged. Native release,
publication and installed acceptance remain pending; consult
[current release status](../RELEASE_STATUS.md) for availability.

## Original 4.46.9 failure

Frozen source `290e6037e775beea5ff6f47d8ffcf6246eefc1db` in
[run 40243385008](https://github.com/Perseusxrltd/mnemion/actions/runs/40243385008)
failed [Windows x64 job 121321047479](https://github.com/Perseusxrltd/mnemion/actions/runs/40243385008/job/121321047479).
At **23:16:27 UTC**, the desktop suite recorded **398 passed, one failed and
two skipped**. Its only failed test was `the five-second native deadline closes
a silent TLS peer`: the elapsed-time assertion required 4,500–5,700 ms.
Packaging did not run, so the later scan-artifact upload also failed because
its file did not exist. This was not a scan finding against a packaged binary.

The original log contains neither the actual sender elapsed time nor the
peer's close time. Its full test duration cannot identify the socket lifetime
or the precise cause of the assertion failure. No installed runtime defect or
specific scheduling/cleanup cause is inferred. Cancellation of the unpublishable
workflow was requested at **23:26:19 UTC**; the original log and request receipt
remain preserved. The earlier [Windows helper lifecycle failure](2026-10-25-windows-telemetry-test-lifecycle.md)
is separate evidence.

## Corrected observation

The [transport test](../../studio/electron/scripts/test-telemetry-transport.mjs)
now timestamps the real peer TCP socket's close and compares it with the
reservation's monotonic deadline, which starts before the sender call. The
existing **500 ms early / 700 ms late** allowance is retained. The fixture
deliberately holds cleanup completion and verifies that the connection closes
and the report is marked closed before the sender promise settles. It verifies
the erased body and cleared lease after cleanup. Cleanup is released and awaited
in `finally`, including on failure.

This uses the actual transport and private policy with a silent local peer;
the transport implementation, timeout and release checks are not relaxed.

| Final focused selection | Result | Duration |
| --- | --- | --- |
| Actual Windows, Node 22.23.4 / Python 3.13.11 | 15 passed, zero failures/skips; exit 0 | 18.8187 s |
| Linux transport tests | 15 passed, zero failures/skips | 10.9982 s |

The Windows receipt finished at **23:26:24.350 UTC** and verified temporary
fixture cleanup. Its real peer closed **9.2023 ms after** the reservation deadline.
The receipt binds 114 inputs, including the corrected test's reviewed hash.
These observations qualify this component test, not installed Electron,
all-platform timing, client resource limits or production ingress.

The earlier Linux log belongs to an intermediate test revision; the final
Linux result above comes from the separate final-source log. Both remain
retained, as does the original failed release.

## Evidence and limits

| Original evidence | SHA-256 |
| --- | --- |
| 4.46.9 Windows x64 release log | `be383308cb8409e8d7d5dc0c8babe42700f32d34734edfee2ecd1858794fb1ec` |
| Release log download receipt | `f13da2e360a4233610647b567538d10edce0151486a8a830a81f5962ff594c98` |
| Cancellation request receipt | `d2b05bc74f7b85fca4f31569dd6134f0ec1189cf7a19df13ded46e3d2b6d57b0` |
| Corrected Windows receipt | `62ad667e26d01a833a6f65f69fcaed29143bb3dd269a0996905cf3cee6875ff6` |
| Corrected Windows test output | `f09fcbadd345c062b7d906cd706255d99fd67590b9b896dd862ed762a858e3ee` |
| Final Linux test log | `08574cf048c7b0c1ec5378e7e869ecb0aecb587db3bff19dc2b6380260357977` |
| Corrected transport test source | `88a0e12f1277d6532332bfa075e38f9daeb899bdad263bd85473b963ef06995e` |

The candidate also retains [managed backup capture](2026-10-25-host-backup-capture.md),
[build portability](2026-10-25-native-build-portability.md),
[collector isolation](2026-10-25-telemetry-collector-service.md) and the separately
tested [closed-week report v2](2026-10-25-telemetry-weekly-volume.md).
Their original evidence keeps its own scope. All 66 requirement texts/states
remain unchanged; V08 is Building, production collection/destination/route
remain false/null/null, and full telemetry acceptance remains open.
