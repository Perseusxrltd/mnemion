# Process readiness across a suspended host's clock change

Recorded **2026-10-12**. The correction is [published in 4.0.14 and verified on
the original shared host](2026-10-12-v414-release.md).

## Actual finding

At 00:43 UTC the existing Windows client reported the original tunnel offline.
After the provider's Computer view reconnected, the same ngrok and service
processes were still present. Public API authentication and MCP recovered, but
the separate Supervisor readiness check reported `children_initialized: false`.

Both managed processes retained their PID, instance, version and model
generations. Their recorded epoch creation time was `1791763609.89`; a fresh
process inspection returned `1791764913.89`, exactly **1,304 seconds later**.
Linux derives that epoch value from a start counter and the host's calculated
boot time. The latter had moved without a process restart. Exact comparison of
those epoch values therefore rejected the original processes.

The interrupted tunnel and clock step were observed together; this evidence does
not establish the provider's sleep policy or provide an always-on hosting guarantee.
A normal managed-service stop/start generated current receipts and restored
readiness. No receipt was edited and no readiness guard was bypassed. The
subsequent ordinary startup updater completed the verified 4.0.13 patch.

## Correction

New Linux readiness and RAM-monitor records bind the process to its kernel boot
ID, PID and raw `/proc/PID/stat` start counter. These remain independent of a
realtime clock correction. Kernel reads are bounded; process names containing
spaces, parentheses or newlines cannot shift the field parser. A different boot,
reused PID/start counter, malformed identity or invalid field type fails closed.
macOS and Windows retain their exact native creation-time comparison.

Older records without this identity retain their original exact comparison.
Malformed new identities never fall back to a legacy timestamp. Instance,
runtime, package, model-generation and second-process-snapshot checks remain.
The legacy timestamp stays present for existing readers; it is not the new
Linux process-birth authority.

RAM-monitor publication uses a monotonic scheduling clock while recording an
ordinary wall-clock observation time. Moving the wall clock backwards therefore
cannot suppress fresh RAM samples until the old wall-clock value catches up.

## Verification and limits

Two focused regressions first failed against 4.0.13: a healthy process lost
readiness after a simulated 1,304-second epoch shift, and the same change hid a
fresh RAM snapshot. A third failing regression reproduced delayed RAM publication
after moving the wall clock backwards by two hours. The correction passes these
checks plus malformed/changed birth records, boot/PID reuse, legacy comparisons,
bounded parsing, private-state handling and existing supervisor controls:
**35 focused local checks passed**. The subsequent complete native and service
release gates passed before publication.
The tests alter test-clock observations only; they do not change the host clock,
start a local model, or operate the user's workspace.

Native release verification and the actual corrected-host observation are
recorded in the [release evidence](2026-10-12-v414-release.md). Existing bootstrap
installations are retained by managed patches; an older operator CLI can still apply its older
readiness interpretation. Inspect new records with the current verified runtime
or current operator package. Updating runtime readiness does not keep a provider's
suspended computer or disconnected tunnel online.

At **01:36:53 UTC**, the original host's ordinary startup launcher was checked
twice after an operator update. It authenticates the active service package and
delegates startup/readiness to that verified runtime, with the existing startup
and updater-operation locks, bounded child output, and no inherited database or
model-provider credentials.
Both checks retained all existing service processes. The host subsequently
updated to 4.0.14 and passed the read-only epoch-shift observation; this does not rewrite older
bootstrap packages or establish a general remote-host delegation product.
