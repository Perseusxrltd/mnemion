# Installed backup-retention form readiness

The [4.12.0 second candidate](https://github.com/Perseusxrltd/mnemion/actions/runs/39217905202)
passed its service, container, dependency and source checks. Its Linux x64
installed test stopped because the expected retention-count field did not
appear after selecting limited retention. Windows x64, macOS ARM and Linux ARM
completed their native checks; the candidate is not a published release.

The retention probe previously located a field without checking whether it
was still connected or disabled. It also accepted a backup panel outside the
intended workspace setup route. The corrected probe scopes the form to that
route, allows its saved settings to render, and waits for editable controls
before dispatching input. These changes address an observed readiness gap;
the log alone does not establish which refresh caused this particular failure.

The Electron TypeScript build and generated-resource checks pass for this
correction. All configured retention, confirmation, unsaved-edit protection,
encrypted-copy verification and repeat-cleanup assertions remain required.
The fresh installed release run, recorded in [release status](../RELEASE_STATUS.md),
must pass before this candidate can be published.
