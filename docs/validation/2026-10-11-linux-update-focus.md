# Linux automatic restart: stale window focus

The unmodified public 4.0.9 → 4.0.10 rehearsal
[38127301901](https://github.com/Perseusxrltd/mnemion/actions/runs/38127301901)
downloaded the target on both Linux architectures but did not restart within
twenty minutes. Both Windows and both Mac targets passed. This established the
requirement for a released fixed Linux client to pass its own public-feed
rehearsal before closing issue 21.

## Controlled diagnosis

The developer workflow copies a hash-verified public AppImage into a new
disposable runner directory. Its modified ASAR/AppImage is a diagnostic artifact,
never a public release. It records actual guards while retaining the official
feed, ten-minute system-idle threshold, draft/transfer checks and normal restart
timer. No personal profile, startup entry or workspace is used.

Timer experiment [38158254138](https://github.com/Perseusxrltd/mnemion/actions/runs/38158254138)
completed upgrades with both original unreferenced timers and referenced timers
on x64 and ARM64. Removing `unref()` was not supported by that evidence; production
timer behavior remains unchanged.

Launch experiment [38159386045](https://github.com/Perseusxrltd/mnemion/actions/runs/38159386045)
identified a mounted x64 AppImage stalled with `focused: true`, despite enough
idle time, a safe renderer and no active transfer. Extracted x64 and both ARM64
cases updated. This led to recording visibility and minimization alongside focus.

Focus experiment [38160824825](https://github.com/Perseusxrltd/mnemion/actions/runs/38160824825)
compared the original focus predicate with one requiring a visible, restored
window. No inspector was attached:

| Architecture / predicate | Observed window state | Outcome |
| --- | --- | --- |
| x64 / original | Focused, invisible, minimized; still blocked at 714 idle seconds | Original 4.0.9 process/file remained |
| x64 / visible and restored | Focused, invisible, minimized | Clean exit, actual 4.0.10 process and correct installed target hash at 626 idle seconds |
| ARM64 / original | Unfocused, invisible, minimized | Clean update at 619 idle seconds |
| ARM64 / visible and restored | Focused, invisible, minimized | Clean exit, actual 4.0.10 process and correct installed target hash at 617 idle seconds |

The two modified predicates progressed in the exact stale-focus state that
blocked the x64 control. Electron can retain its focus flag after minimization;
that flag alone is therefore not a reliable indication of active window use.

## Source change and safety boundaries

The production restart policy now blocks a focused window only while it is
visible and not minimized. The ten-minute system inactivity threshold, enabled
update preference, verified download, renderer draft protection, active transfer
and native-host shutdown/recheck conditions remain in force. A visible restored
focused window still blocks restart. Both automatic entry and the post-shutdown
recheck use the same policy.

The Electron suite passed **67 tests**. The added regression exercises hidden,
minimized and combined stale-focus states; disabling updates, missing downloads,
insufficient/invalid idle time, unsaved work and active transfers still block each
case. The native installed/update suites remain required for the release.

This source fix cannot change restart logic already executing in an older
installed application. An affected older AppImage may need one ordinary **Quit
Mnemion Studio** to apply its downloaded update, or installation of the newer
official download. A released fixed client must then demonstrate an unattended
upgrade to a subsequent release using unmodified public files. Developer
comparison success does not close that acceptance gate.

## Published follow-up

The unmodified public **4.0.11 → 4.0.12** rehearsal subsequently passed on both
Linux architectures and all four Windows/Mac targets. It retained the normal
idle/work guards; Linux x64 recorded 620.29 seconds of real X11 inactivity and
the new running process/version. This completes the issue's remaining acceptance
gate. See [the release and public upgrade evidence](2026-10-11-v412-release.md).
