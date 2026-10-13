# Managed update scheduling validation — 2026-10-13

The 4.1.7 source addresses
[issue 33](https://github.com/Perseusxrltd/mnemion/issues/33): the reported host
experienced about 16 hours of wall time but only 5.4 hours of monotonic time,
so its healthy updater had not reached its six-hour check deadline.

The watcher now schedules both wall-clock and monotonic deadlines. Either can
trigger a check after a maximum 30-second monotonic retry floor. Normal polling
remains ten seconds; startup jitter remains 60–120 seconds. Checks keep their
six-hour default with 10% jitter, and busy connector leases retain a 30-second
retry. The host's private `schedule.json` records the actual wall-clock deadline
and attempted check time, including failed attempts. It does not persist a
monotonic deadline that would become meaningless after reboot.

**43 focused tests passed** using bounded local processes and temporary state.
The running watcher was exercised with frozen monotonic time and with wall time
moving backward; the second check occurred on its first ordinary loop after
each simulated correction. Other cases cover repeated forward corrections,
failure diagnostics, disabled checking, legacy deadline estimates, malformed
state, signed updates, unchanged schema rules and connector lease coordination.
Another **17 checks passed** for managed process restart and a real verified
database backup, release publication rules and the agent operation contract.
The two conditional installed-package scenarios are left to the release CI
configuration. Repository lint and formatting passed for 391 files; package
versions, generated API version and changed documentation links also passed.
This is a controlled clock simulation, not a claim of suspending the user's
actual VM or installing the new release there.

Release packaging, independent uploaded-artifact verification, public-feed
upgrades and live product-page checks remain separate publication gates.
The [full product checklist](../PRODUCT_REQUIREMENTS.md) remains open, including
individual sign-in, hosted OAuth, independent host recovery, connected capture,
retrieval quality and the encrypted secrets vault.
