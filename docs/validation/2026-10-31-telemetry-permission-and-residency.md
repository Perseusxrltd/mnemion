# Python permission reads and Linux residency snapshots

**31 October 2026 — reviewed source and focused checks.**
The reviewed changes are adopted in `ae20137ad8e9ef8f4d362a85fa033530f22b6ad2`
(Python permission read) and `2d954b2d5cc551469a2d87ee0c073458b5de484c`
(Linux snapshots). Their patches match the original Grok changes, both based
on `c8ca44ba07ceb1d3bdf4b93efb0993478c0e909b`.
This record does not establish publication or installed qualification.
Production collection remains off; V08 stays Building and all 66 requirement
states are unchanged.

## Source behavior

Python `begin` and `begin_choices` now use a fresh read-only preference/company
stamp rather than full settings status. They omit pending-count, delivery-ledger
and disclosure-document reads. No connection, statement or positive permission
cache survives that read. Persistence and delivery independently recheck the
saved choice, disclosure, revision, generation and company restrictions.

With valid preferences and company policy, damage confined to the delivery
ledger can still allow a bounded local aggregate. Full status then reports
`storage_unavailable` and `effective_enabled=false`; preview returns no aggregates.
This is not a saved opt-out or proof of an empty disk queue. Delivery still
rejects the damaged ledger. Queue writes apply normal expiry before checking
the retained rows. The privacy-page message now describes unconfirmed privacy
and delivery state without promising that no aggregate exists. The
[collection contract](../implementation/anonymous-product-telemetry.md) and
[controls guide](../guides/product-telemetry-controls.md) retain these boundaries.

Linux diagnostics keep `first_linux_residency`, `last_linux_residency` and
`sampled_rss_peak_residency` for each PID plus creation-tick identity. Each
snapshot keeps `VmRSS`, anonymous, file and shared bytes from one status read;
the sampled peak selects the greatest observed `VmRSS`, retaining the earlier
sample on a tie. It does not pair a later breakdown with an earlier `VmHWM` or
combine component maxima. Copies prevent later observations or caller mutation
from changing an earlier result. Windows/macOS fields stay null; real zero
stays zero. Missing or malformed status fields still reject the whole read.
The [accounting contract](../implementation/telemetry-owned-launch-accounting-2026-10-30.md)
keeps cgroup memory, per-process RSS and kernel high-water marks separate.

## Original checks and corrections

- **Producer:** the original command was refused before execution; an alternate
  incomplete Windows environment failed collection because `jsonschema` and
  `cryptography` were absent. Product tests did not run there. The original WSL
  focused run had **177 passed, 2 failed in 41.35 seconds**. One oversized-queue
  fixture used day 20000, so expiry removed its rows before three new aggregates
  were stored. The CLI unreadable fixture mocked `status`, which the new producer
  path no longer calls. The committed corrections use current-day surviving
  rows and an injected `_connect` error, and separate ledger-only persistence
  from delivery refusal. The three corrected cases passed once: **3 passed in
  3.93 seconds**. They cover surviving queue bounds, ledger-only persistence
  with delivery refusal, and the CLI unreadable-store case. This retains the
  original 177 passes; no full 180-test rerun is claimed. Ruff formatting and
  lint passed on the three changed Python files.
- **Linux:** the first new fixture had **1 failed, 45 deselected in 1.43 seconds**.
  JSON rounding of `2**62 + 1` made its invalid-value expectation disagree across
  Python and Node; the fixture now uses `2**63`. Its original corrected run had
  **1 passed, 45 deselected in 0.66 seconds**. The affected suites then ran once:
  **61 passed in 7.15 seconds**. This includes the existing small Windows adapter
  self-check; it is not a native Linux or installed-app run. The direct Ruff
  module was unavailable; the cached offline tool passed lint and reported all
  three Python files already formatted.

## Remaining acceptance

No new residency read, poll interval or persistent sampler was added. Linux
whole-lifetime and unseen/exited-process coverage remain incomplete. A member
with unreadable creation ticks is still skipped; `identities_missing` remains
null. These snapshots do not close that existing gap.

The telemetry allowance stays **8 MiB per participating process and 0.5% of one
core**, unaccepted and not compared by this work. No CPU/RAM saving is measured.
The standing [whole-product efficiency requirement](../implementation/runtime-efficiency.md)
includes low idle/tray CPU and RAM; telemetry's allowance is not a whole-app
budget. Representative installed measurements, complete process coverage and
production privacy/collector acceptance remain open.
