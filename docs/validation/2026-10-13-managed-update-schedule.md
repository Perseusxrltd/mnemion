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

[Mnemion 4.1.7](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.1.7)
was published at **10:10:04 UTC** from
`6ffe57feeadc5bac87a4ea49fc0c0b76a9357a70`.
All 30 [release jobs](https://github.com/Perseusxrltd/mnemion/actions/runs/38376759129)
passed, including the six installed workspace and automatic-update targets.
The separate [product checks](https://github.com/Perseusxrltd/mnemion/actions/runs/38376736278)
also passed. The duplicate native push workflow was intentionally cancelled;
the release workflow's complete native gates passed.

The [independent verifier](https://github.com/Perseusxrltd/mnemion/actions/runs/38381310385)
validated all 38 uploaded assets against the production validator from that
exact source commit. Its [receipt](2026-10-13-v4_1_7-hosted-verification.json)
records **3,865,704,241 bytes** with unchanged asset IDs, sizes and digests.
The checksum inventory SHA-256 is
`6d22ff09c45e42099ef76da1cd2a36c9fbb4e2e256e903de7101747c0c50d48b`.
The [10:10:07 public check](2026-10-13-v4_1_7-publication.json) confirmed the tag,
latest stable release and all 12 anonymous checksum and update feeds.

[Website synchronization and verification](https://github.com/Perseusxrltd/mnemion/actions/runs/38381497133)
completed automatically. The [live HTML receipt](2026-10-13-v4_1_7-website.json)
confirms the visible version, every primary installer, current notes and guides,
checksums, roadmap on `main` and homepage product link. No new website design
or visual render is claimed. All six [public 4.1.6 → 4.1.7 upgrade rehearsals](https://github.com/Perseusxrltd/mnemion/actions/runs/38381497073)
passed by **10:21:17 UTC**. Their [sanitized receipts](2026-10-13-v4_1_7-public-upgrades.json)
confirm unchanged official packages, real system idle, process replacement,
preserved profiles and active sandboxes; both Linux login entries track the
newly installed image. Starting installer hashes match the independently
verified 4.1.6 packages for the corresponding platform and architecture.
Issue 33 is closed. These hosted checks do not claim that the user's desktop
or separately hosted server has already installed the patch.

The [full product checklist](../PRODUCT_REQUIREMENTS.md) remains open, including
individual sign-in, hosted OAuth, independent host recovery, connected capture,
retrieval quality and the encrypted secrets vault.
