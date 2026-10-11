# Actual Windows desktop update observation

Observed **2026-10-11**, using an existing ordinary x64 Windows installation.
Private user paths, process IDs, workspace addresses and keys are excluded from
this public report.

## Result

The unmodified official **4.0.9** app downloaded, authenticated, installed and
relaunched official **4.0.10** without invoking the installer manually or
changing its inactivity/draft guards. The installed ASAR version was 4.0.10
afterward, with a new running app process. Automatic updates, background mode
and login startup preferences remained enabled; the Windows login entry was
present.

The app was initially not running. Its update mechanism therefore could not
check or install until it was launched. The observation does not establish why
the earlier process had stopped or prove a future machine-boot test.

## Checks

- Verified the public update manifest against the trust key embedded in the
  original installed application and verified the complete downloaded installer
  against the manifest's authenticated SHA-512 and size.
- Started the original executable in background mode with no smoke, debugging
  or test flags. A read-only observer recorded real OS inactivity, process
  replacement and the installed package version.
- The old process remained at 18:30 UTC, exited during installation around
  18:31 UTC, and the replacement app was running with version 4.0.10 by
  18:32 UTC. The observation did not synthesize computer inactivity.
- Retained the actual profile and verified preferences after replacement.

This is evidence for the Windows x64 **4.0.9 → 4.0.10** path only. It does not
close Linux issue 21, verify unreleased native local hosting, or prove remote
workspace stress acceptance. The configured remote host was offline during
the subsequent connection attempt; recovery preparation is recorded separately
from a successful connection.

The 4.0.11 candidate also improves update visibility and offers an explicit
guarded **Restart to update** action. That source change requires its own
installed release checks; it was not involved in the observation above.
