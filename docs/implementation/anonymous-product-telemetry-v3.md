# Anonymous product telemetry — gated v3 reference

**V08 remains Building.** Collection stays unavailable. The current source
includes the v3 clients, collector and private maintainer reports. The ordinary
privacy-settings page shows local controls; it does not show fleet data.
No fleet statistics can be pulled while collection stays off.

The [30 October compiled-app review](../validation/2026-10-30-telemetry-v3-app-review.md)
qualifies run 40981256191 on this source. Ten controls passed in the unpackaged
compiled Linux app (Electron 44.9.3, Node 24.22.0, x64), and one inspected
25-byte v3 packet matched fixture delivery. The first private reader wrongly
required `comparison: false` in `source.json`; the corrected three-field reader
accepted that same original with no rerun. That scope is the compiled Linux
source app. Installed delivery, resource gates, whole-wire measurement, and
hosting or provider acceptance stay open.

An idle SQLite connection is rejected for this release. Finite Node probes saw
other-process commits, and the per-operation baseline could be replaced on
Linux Node 22.22.0 and Windows Node 25.2.1. Both retained Windows handles
blocked atomic replacement with `EPERM` and kept the old generation. The
[30 October lifecycle note](../validation/2026-10-30-telemetry-sqlite-lifecycle.md)
records those standalone probes. They are not Electron builds or resource
measurements. No eligible existing owner was identified. The backend is
unavailable for remote-only, onboarding-only, and tray-only lifecycles. The
2 MiB and 0.5% ceilings stay unchanged. No new resource run is justified.

Attribution run 40971963055 made no enabled reservations and remains
unexplained. Run 40976743563, on source `7ee617691ead16c17bbdb9eb797e03f20f186325`,
completed all six compiled Linux journeys. Both enabled guards were `allowed`
and each sent one 25-byte v3 report. The controls sent none. That success does
not account for 40971963055. The admission trace still changes no production
behavior. No small redundant cut was found inside the fresh per-transaction
store, activity, delivery or transport paths. The first `sqlite.open` rose
1,179,648 RSS bytes in both enabled repeats; the transport windows rose
1,908,736 and 1,826,816 bytes while `heapUsed` fell. Those windows are not gate acceptance.
The 2 MiB and 0.5% gates stay unaccepted, and `resource_acceptance` stays false.
The measurement limits are in the
[29 October resource note](../validation/2026-10-29-telemetry-v3-resource.md).

The approved direction is a trusted first-party collector and
publication-side differential privacy. That is a different promise from wire
v2. v2 randomizes one category on the client and the collector cannot read it.
v3 sends a bounded summary. The collector sees that summary long enough to add
it to fixed counters, then drops the bytes. The published week is noisy.
Privacy from the published file is not privacy from the collector, and it says
nothing about provider logs. Those still have to be qualified before any route
is turned on.

`default_enabled` remains true. `collection_available`, the destination and the
release route remain false/null. The dedicated collector still defaults to
legacy `/v1/report`. `CollectorV3` is mounted only when that process is started
with `--mode v3`, on `/v3/report`, writing `reports-v3.sqlite3`. The Electron,
browser and Python client paths use v3, behind the existing permission and
budget gates. No production host or collection route is enabled by this change.

## What one report contains

The contract is [`wire-v3.json`](../../mnemion/product_telemetry/wire-v3.json).
The packet is 25 bytes, inside the existing 64 KiB attempt reservation and the
256 KiB daily wire guard. It is not a measured installed-wire result.

Each report carries every catalog metric at once: feature family, feature,
outcome, result and work items, failure reason, latency, queue, payload bytes,
tokens, stored bytes, wire bytes, throughput, CPU, resident memory, the
configured memory budget and queue drops. A company-disabled group is the
explicit bin `group_disabled`. An enabled group with no accepted observation is
`sensor_missing`. Neither is stored as a fake zero.

The weight of one report is one tick per metric, after per-bucket clipping at
255 and a single draw proportional to those clipped counts. The tick is not an
uncapped event total. The same report also adds one denominator tick, on
exactly one cohort of the axis that report chose. The L1 change of the whole
released vector is therefore 20: 19 metrics plus the denominator. Other
coordinates stay still. A hostile packet that fails the fixed layout is
rejected. A valid packet cannot add a second tick, a second axis, or a new
cohort name.

## Cohorts in one week

Each report chooses `release` or coarse `os` with equal probability. The draw
is the first `secrets.randbelow` call on the summary path, before the
observations are read. Tests can pass `random_below`; a packet, header, or
deployment flag cannot. The packet stores only the chosen marginal. Both axes
are accepted in the same week. There is no server-week parity and no joined
release-by-OS profile.

The release allowlist is operator-owned. Preparing a release adds the current
source version and the target stable version, keeps at most 32 coordinates, and
packs slots from zero. A coordinate that is not on the allowlist at summary time becomes
`unlisted`. The packet cannot invent a slot. It stores the major, minor and
patch bytes, not the slot. Components are integers from 0 to 255. The coarse OS
names are `windows`, `macos`, `linux` and `other`.
A report never contains a hardware id.

The closed report freezes that week's domain: the release slots, the unlisted
slot, the four OS names, and the metric legend. Schema version inside this
report is 2. Validation reads that embedded legend. It does not rebuild the
cohort list from the allowlist compiled later. Adding or retiring an allowed
release therefore does not move the unlisted slot of a report that is already
closed, and it does not make that report fail. Identifiers are not free text.
A release id must equal `major.minor.patch`, slots are packed from zero, the
unlisted id is exactly `unlisted`, and the OS list is exactly those four names
in that order. Ordered legend bounds are strictly increasing integers. Their
count and unit must match the compiled metric; the stored edges are the ones
used to read that report. A category row stores only its id and kind.
Category names are not in schema 2. Export reads those names from the current
wire-v3 catalog, so a later rename of a category string is not preserved.

The published vector contains the full fixed domain of both axes, including
cohorts that received nothing. Global figures are the sum of that one noisy
vector. They are not a second query. Release rows and OS rows stay separate
marginals.

The seven-attempt week and the 24-hour minimum gap stay in the existing client
budget. The collector cannot check them, and they do not prove distinct
installations.

## Admission

Every well-formed report is admitted. The window does not keep a first-M list
and does not evict another report to make room. Inserting one report therefore
cannot remove a different accepted report. The earlier cap-2 counterexample,
where one inserted report moved the vector by 40, came from that eviction.
With eviction gone, the same insertion moves the vector by 20.

Clipping still happens inside the admitted report. The protected unit is
add-or-remove one input report, including that admission and that clipping.
The epsilon below is the end-to-end bound on the released vector. It is not a
bound that starts only after a report has already been accepted.

A flood can make the sealed JSON larger than the store accepts. That week is
not sealed a second time. The failure is recorded as
`{window_week, state: publication_failed}` with no report body, cohort id, or
count.

## Publication noise

Noise is the difference of two geometric random variables with continuation
probability `16452/17381`. Production draws use `secrets.randbelow`. The
integer sampler is the privacy mechanism. A rounded continuous Gaussian is not
used: finite samples of a continuous distribution can leak privacy through
ordinary numerical error (Canonne, Kamath, and Steinke, "The Discrete Gaussian
for Differential Privacy", arXiv:2004.00010).

For one coordinate, a unit shift multiplies the likelihood by at most
`17381/16452`. Across an L1 change of 20, the likelihood ratio is at most
`(17381/16452)^20`, which is at most 3. Integer arithmetic checks
`17381**20 <= 3 * 16452**20`. The add-or-remove-one-report epsilon is therefore
at most `ln(3)`. Rounding (quantum 1), suppression, global sums and quantile
labels are functions of the noisy vector, so they do not increase that epsilon.

The bound is per report. It is not a per-person weekly budget. Up to seven
reports can leave one installation, and the collector cannot tell. Linked
reports would compose. This candidate does not claim they are unlinkable at
the collector.

One noise coordinate has standard deviation about 25.7 and a 95% half-width of
55. That half-width is a tail of one noise coordinate. A sum of cohort
histograms adds one independent noise per cohort, so its spread is larger.
The half-width is not a confidence interval for a percentile.

## Suppression and quantiles

Suppression is per axis. A cohort is grouped only when its **noisy**
denominator is below 64 and at least one other cohort on the same axis is also
below 64. The grouped cohorts are published as one remainder, with their ids
but not their separate counts. A release remainder is not added to an OS
remainder. A single small cohort stays visible, because hiding exactly one
cohort would let a reader recover it from the axis sum. The threshold is not
applied to the raw count.

Ordered metrics can publish `p50` and `p95` as catalog bucket bounds. The rule
is not "read a quantile from the noisy histogram." That non-private read is
what put the counterexample's p95 in the 0–9 ms bucket: the histogram
`[0, 0, 200, 50, 0, 0, 0, 0, 0, 0]` has 20 percent of its nonnegative mass in
10–49 ms, so the fixed histogram's own p95 is the 10–49 ms bucket, and the old
peak label said 0–9 ms (Gastaud and Sarus, "Estimating a cumulative
distribution function with differential privacy", 25 November 2020, describe
the histogram-then-non-private-quantile step this label does not use).

The replacement builds a box around the measurement bins. For one cohort the
radius is the exact discrete-Laplace tail, widened until a union bound over
the bins is at most 1/20. For a sum of cohort histograms the radius is a
Chernoff upper bound on the sum of those independent noises, plus one count.
Every histogram inside the box has to place that percentile in the same
catalog bucket. Otherwise the state is `insufficient_precision`. Both outcomes
carry `mechanism_envelope_not_a_percentile_confidence_interval`. The file does
not contain an exact millisecond or byte quantile, and a single-coordinate
half-width is not reported as a percentile guarantee.

## Retention

A closed week is sealed once. The counters are then zeroed. The next week has
a new counter vector. There is no overlapping raw pool and no per-client row.
`reports-v3.sqlite3` keeps at most eight immutable weeks. Inserting the same
week again fails. The body is the protected JSON. v2 `reports.sqlite3` and
report schemas 1–4 are untouched and still validate on their own rules.

The reviewed one-axis 32-release body was 209,365 bytes and did not fit a
65,536-byte store. The store now accepts a report of at most 786,432 bytes.
The database limit is 7,340,032 bytes, which is above eight of those reports,
on 4,096-byte pages. The focused check seals the supported domain of 32 listed
releases plus `unlisted` plus the four OS cohorts, with 200 ticks on each
listed release, and stores eight copies. The same seal measured 215,576 bytes
on 29 October, above the old 65,536-byte limit and inside 786,432. A body the store rejects does not
disappear quietly and is not drawn again.

## Maintainer export

```text
python -m mnemion.product_telemetry.server serve --state <absolute dir> --certificate <absolute pem> --private-key <absolute pem>
python -m mnemion.product_telemetry.server serve --mode v3 --state <absolute dir> --certificate <absolute pem> --private-key <absolute pem>
python -m mnemion.product_telemetry.maintainer_v3 --state <absolute dir> --format json
python -m mnemion.product_telemetry.maintainer_v3 --state <absolute dir> --format csv
python -m mnemion.product_telemetry.maintainer_v3 --state <absolute dir> --format html
python -m mnemion.product_telemetry.maintainer_v3 --utility --format json
```

The first serve command is legacy `/v1/report` and `reports.sqlite3`. `--mode v3`
is the only switch that mounts `CollectorV3` on `/v3/report` and opens
`reports-v3.sqlite3`. Default bind is `127.0.0.1:8443`. Optional flags stay
`--bind`, `--port` and `--systemd-socket`. A bad flag, path or credential is a
fixed error. It is not echoed. Export reads an absolute directory that already
contains `reports-v3.sqlite3`. A mistyped directory does not create an empty
database. JSON and CSV are unchanged. HTML is a self-contained file for the
operator: one week control, then release or operating system, never both as one
profile. It shows the nineteen metric distributions, the noisy denominators,
p50 and p95 only as stored bucket bounds, and publication failures. An empty
store still opens, with that fact stated.

The summary says the export is not the local privacy page, that ticks are not
people, and that the noise is not an independent-user or causal interval.
Publication failures appear as the week and the fixed state, without cohort
ids or counts. Bucket labels for an ordered metric come from the legend stored
in that report. `--utility` prints the model below. It does not read a fleet.

## Modelled utility

Assumption: every modelled installation shares one release and one coarse OS,
and each report chooses one of those two axes with probability 1/2. The
expected ticks on one axis are half the report ticks. The sampling spread is
the binomial standard deviation `sqrt(N) / 2`. "Usually published" means that
lower screen, the mean minus two of those standard deviations, is at least
`64 + 55`. A bucket is called usable only when its share of that same lower
screen is at least `110`. The printed model frequency of clearing 119 is not
that screen and is not a guarantee. The table is about one cohort coordinate.
The global sum is noisier.

| Installations | Reports each | Report ticks | Expected on one axis | Denominator usually published | Majority bucket usable | Even 8-bucket split usable |
| --- | --- | --- | --- | --- | --- | --- |
| 10 | 2 | 20 | 10 | no | no | no |
| 10 | 7 | 70 | 35 | no | no | no |
| 100 | 2 | 200 | 100 | no | no | no |
| 100 | 7 | 700 | 350 | yes | yes | no |
| 1000 | 2 | 2000 | 1000 | yes | yes | yes |
| 1000 | 7 | 7000 | 3500 | yes | yes | yes |

At 10 installations the mechanism cannot support a product comparison. At 100
installations and 2 reports, the lower side of the axis split stays under the
publish bar. The model frequency of one axis reaching 119 is 0.004361. That
frequency is not the publish flag and not a guarantee. Seven reports clear a
cohort total and a coarse majority bucket in this model, and an even split
across eight buckets does not. At 1000, the
lower side of the split still clears the total, the majority bucket, and the
even split. None of those cells is a guaranteed observed count. Seven reports
require seven locally spaced attempts. Two is a sparse model.

## Client preparation

The three clients already reserve a bounded pending snapshot of `(cell, count)`
rows. `prepare` in `wire_v3.py` and `TelemetryWireV3` in
`studio/electron/telemetry-wire-v3.ts` turn that snapshot into the same 25-byte
packet as `summarize`. The TypeScript helper takes the reviewed wire contract
and catalog from its caller. It does not open a config file.

Counts are added once and clipped at 255 per bucket. A count is not expanded
into repeated observations, and the encoder does not rebuild a raw event. At
most 512 rows are accepted. The release-or-OS coin is the first
`secrets.randbelow` or `crypto.getRandomValues` draw, before any row is read.
A test may pass draws; a packet cannot. No local randomizer runs on this path.
The collector still sees the summary. Publication noise stays on the closed
week, which this client step does not change.

`no_failure` is only the clipped mass of `success` and `accepted`. The catalog
forbids a failure reason on those two outcomes, so a missing reason cell there
is the `none` reason. A `failed`, `deferred`, or other outcome with no reason
cell is unresolved. That residual competes as `sensor_missing`. It is not
rewritten into `no_failure`. If reliability is disabled, the reason bin stays
`group_disabled` even when a reason was observed.

Python, Electron, and browser senders call these helpers when a report is
prepared. Manual review, the final group check, opt-out, company policy, and
the delivery budgets stay in front of that call. The request path in source is
`POST /v3/report` with a 25-byte body. Disclosure version 2 describes a
collector-visible summary. Collection remains off: `collection_available` is
false, the destination is null, and the release route address is null.
The dedicated server defaults to legacy `/v1/report`; `--mode v3` mounts
`/v3/report`. A v3 packet is not sent to the legacy route.

## Still required before any activation

- Installed qualification of the Electron, browser and Python v3 paths, behind
  the same opt-out, company, GPC, metering and 7-per-week gates.
- A qualified host. The dedicated collector can select `--mode v3` in source.
  No host was changed or started, and ingress, TLS, log and backup
  qualification for an operated path remain open.
- Provider retention qualification. Disclosure version 2 explains that the
  collector sees bounded summaries and noise protects the published week. It
  does not claim that provider retention has been inspected.
  `collection_available`, destination and route stay false/null/null.
- The installed 2 MiB / 0.5% resource gates. This packet is 25 bytes in source.
  That is not an installed measurement. Run 40976743563 is an unpacked Linux
  attribution journey, not those gates. The failed full-app trials were not
  rerun, and run 40971963055 is still unexplained.
- The private HTML file is a local maintainer export. It is not an
  unauthenticated report endpoint and it is not added to ordinary privacy
  settings.
- Field 47 and the connector migration are a different change and were not
  touched here.
