# Background presentation after an update

Recorded 29 October 2026 for **4.46.52 source**. The
[actual 4.46.46 → 4.46.49 update](2026-10-29-windows-44649-update.md) succeeded,
but its minimized window returned visibly without taking the foreground.
That installed observation remains unchanged.

The source correction in `studio/electron/update-relaunch.ts`, `updates.ts`
and `application.ts` records the intended presentation immediately before the
installer handoff and consumes it once when the matching version opens:

| Restart with background mode enabled | Presentation after relaunch |
| --- | --- |
| Automatic | Background |
| Deliberate, from a visible and restored window | Visible |
| Deliberate, from a hidden or minimized window | Background |

Background presentation uses a minimized taskbar window on Linux and a hidden
window on Windows/Mac. A newer disabled background preference takes precedence.
The hint expires after one hour; stale, malformed or version-mismatched hints
are discarded without changing ordinary startup. A hint that cannot be consumed
is not applied. This is presentation state only: draft, activity, publisher
verification and installation gates remain unchanged.

The app starting the update must contain the new handoff code. Receiving
4.46.52 from an older client cannot reconstruct that client's window state.

| Focused qualification | Result |
| --- | --- |
| Linux, Node 22.22.0 | 65 passed, zero failed/skipped |
| First Windows invocation through a UNC path | Test discovery failed before any cases ran |
| Windows local fixture, Node 25.2.1 | 57 passed, zero failed, eight Linux/POSIX cases skipped |

The Linux receipt binds all six implementation/test source hashes. The corrected
Windows fixture records byte-identical test and compiled files; the original
discovery failure remains separate. These Node checks cover the handoff,
consumption and controller guards. They do not replace packaged Electron,
native installer or actual post-update window acceptance, which remain pending.
All 66 requirement states are unchanged; issues 44/47/48 remain open, and V08
is Building with telemetry collection off.

| Retained evidence | SHA-256 |
| --- | --- |
| `linux-tests.json` | `50ce4367c1abd44bd8114a82f80a1087eb352d1a37b9f4540b3e4eb1f63b5a40` |
| Original `windows-tests.json` | `b82b457fc4196c723f914c3d075bdbc28a8a8aa85c9839c577529c9389c4562e` |
| `windows-local-tests.json` | `8f333b2c685943d59e07cc39cb28df7f6b06b09e5dd1f278e204a80881229243` |
| `windows-fixture.json` | `29ba4083d26d074f64d2bba1385e330ccad32072162109c4ecf25a584ba92779` |
