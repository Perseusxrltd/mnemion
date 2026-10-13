# Windows background update and lock-screen follow-up

On 13 October, the actual installed Windows app completed an automatic
**4.1.4 → 4.1.6 → 4.1.7** update sequence. Read-only observations recorded the
installed version, disappearance of the preceding process and stable relaunched
processes. The operator used normal update-check and background-window controls;
there was no forced installer launch, idle-clock substitution, profile reset or
update-policy change. See the [sanitized observation](2026-10-13-windows-v417-auto-update.json).

The second downloaded update remained staged while Windows was locked, with
more than 16 minutes of real inactivity and a visible reopened application.
Windows session information confirmed the lock. Sending the application's
normal Close action, with its existing background preference enabled, hid that
window and allowed the ordinary updater to install 4.1.7 and relaunch.

The 4.2.0 candidate corrects the retained-focus case: when the operating system
reports a locked session, a visible focused window does not count as active use.
The ten-minute inactivity threshold, draft/transfer checks, administrator policy,
service shutdown and final pre-installation checks remain required. Unlocking
during shutdown or at the final installer check cancels the automatic restart.
Unknown lock state stays conservative. The API used is Electron's documented
[system idle-state observation](https://www.electronjs.org/docs/latest/api/power-monitor#powermonitorgetsystemidlestateidlethreshold).

**129 Electron checks passed**, including the locked-window policy and
unlock-during-shutdown/install races. The native update fixture also covers the
locked-focus and subsequent unlock cases with controlled idle/lock observations;
native installation, signatures and relaunch remain real operations. The final
six-platform release run must still pass this expanded fixture.

The live Windows observation exercised the published 4.1.x updater. It is not
proof that an unreleased 4.2.0 installer or its database migration has passed.
It also does not by itself verify a new authenticated workspace connection.
