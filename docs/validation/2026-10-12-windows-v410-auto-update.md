# Actual Windows automatic update — 2026-10-12

The user's installed Windows x64 app automatically upgraded from **4.0.13 to
4.1.0** through the normal public release feed. Its regular background check
downloaded the installer; after the normal ten-minute inactivity guard, the old
app exited, the installer ran and the new version relaunched. Two observations
confirmed the new running version by **07:56:05 UTC**.

Automatic updates, background operation and login startup stayed enabled. The
observer did not request an update, force a restart, change preferences or
simulate inactivity. Windows was locked during installation. See the
[allowlisted observation record](2026-10-12-windows-v410-auto-update.json).

At **08:05:32 UTC**, the updated client's credential helper successfully opened
the existing protected administrator connection. Two authenticated read-only
requests verified the same independent administrator and the shared server's
runtime observations. This performed no memory writes or model requests.

The shared service remains on **4.0.14**. Its controlled schema migration has
been rehearsed and a fresh encrypted backup was preserved and decrypted on
Windows, but the Windows lock screen interrupted interactive access to the
provider's host console before migration began. If the backup freshness window
expires, another preserved backup and Windows verification are required before
applying the migration. Desktop installation does not upgrade a separate host.

The [public release record](2026-10-12-v410-release.md) also includes successful
4.0.14 → 4.1.0 unattended update rehearsals on all six desktop targets.
