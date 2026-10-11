# Native foreground-window verification

Investigated **2026-10-11** after Windows x64 installed-workspace acceptance
passed but the subsequent update rehearsal failed its focused-window assertion.
The failing release attempt was
[38170619565](https://github.com/Perseusxrltd/mnemion/actions/runs/38170619565),
at `a758325635973dc51dc81cb635324885c802ab8a`. That attempt is not a releasable gate.

The rehearsal launched its GUI process with `windowsHide: true`, then waited
only for `isFocused()`. The production update policy checks actual visibility
and minimization as well as focus, because hidden/minimized windows may retain
the focus flag. A focused flag alone therefore did not establish the test's
foreground-window precondition.

A native Windows diagnostic reproduced this with the same **Electron 44.7.0**
runtime. Its cached archive was verified against the upstream SHA-256 inventory.
It used a temporary profile, four sequential cases, a 600 MiB Windows job memory
limit and fixed process deadlines. No Mnemion installation, memory workspace,
model or update was started by that diagnostic.

| Native launch and window setup | Focused | Visible | Minimized |
| --- | --- | --- | --- |
| Hidden startup; original show/focus sequence | true | false | false |
| Hidden startup; restore/show/focus sequence | true | true | false |
| Normal GUI startup; original sequence | true | true | false |
| Normal GUI startup; restored sequence | true | true | false |

These states persisted before and after a real renderer round trip. Hiding the
window afterward produced a background state. All diagnostic processes exited
and their temporary profiles were removed.

The Windows rehearsal now allows the actual GUI to show, explicitly restores
the window and waits for visible/restored/focused state before invoking the
guard. It records native state before and after that check and during workspace
shutdown. The Mac fixture also verifies all three state properties. **Production
restart policy is unchanged.** Draft, transfer, inactivity, shutdown and signed
installer checks remain release requirements. The new complete native update
and relaunch run is still required; the diagnostic alone is not update acceptance.
