# Anonymous product telemetry — gated v3 reference

**Not a V08 completion.** Collection stays unavailable. This note describes a
reviewable backend candidate beside wire v2. It does not authorize a production
upload, a disclosure change, or a claim that an ordinary privacy-settings page
shows fleet data.

The approved direction is a trusted first-party collector and
publication-side differential privacy. That is a different promise from wire
v2. v2 randomizes one category on the client and the collector cannot read it.
v3 sends a bounded summary. The collector sees that summary long enough to add
it to fixed counters, then drops the bytes. The published week is noisy.
Privacy from the published file is not privacy from the collector, and it says
nothing about provider logs. Those still have to be qualified before any route
is turned on.

`default_enabled` remains true. `collection_available`, the destination and the
release route remain false/null. `server.py` still serves only `/v1/report`.
The reference ingress is `CollectorV3` on `/v3/report`, constructed in process.
Nothing in the client sends a v3 packet.

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
uncapped event total. The same report also adds one denominator tick. The L1
change of the whole released vector is therefore 20: 19 metrics plus the
denominator. A hostile packet that fails the fixed layout is rejected. A valid
packet cannot add a second tick, a second axis, or a new cohort name.

## Cohorts

Even server weeks accept a public release coordinate `(major, minor, patch)`,
each component an integer from 0 to 255. Odd weeks accept one coarse OS:
`windows`, `macos`, `linux` or `other`. The choice is the public week number,
not the measurements. A packet for the other axis is rejected and not kept.

The release allowlist is operator-owned and currently has one slot:
`0` means `4.46.53`. That coordinate keeps that meaning when a later release
appends another slot. A coordinate that is not on the allowlist becomes
`unlisted`. The packet cannot invent a slot. A report never contains both a
release and an OS, and it never contains a hardware id.

Global figures are the sum of that week's noisy cohort vector. They are not a
second independent query, and a release week must not be joined to an OS week.

The seven-attempt week and the 24-hour minimum gap stay in the existing client
budget. The collector cannot check them, and they do not prove distinct
installations.

## Publication noise

Noise is the difference of two geometric random variables with continuation
probability `16452/17381`. Production draws use `secrets.randbelow`. Tests can
pass a `random_below` callable to the window or the reference collector. No
header, packet field, or deployment flag selects that callable.

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
55. The same half-width on a sum grows with the number of cohorts that were
noised. Empty allowlist slots are why the week uses only one axis.

## Suppression and quantiles

A cohort is grouped only when its **noisy** denominator is below 64 and at
least one other cohort is also below 64. The grouped cohorts are published as
one remainder, with their ids but not their separate counts. A single small
cohort stays visible, because hiding exactly one cohort would let a reader
recover it from the global sum. The threshold is not applied to the raw count.

Ordered metrics publish `p50` and `p95` only as catalog bucket bounds, and only
when one measurement bucket holds the mass beyond the noise half-width and
every other measurement bucket is inside that half-width. Otherwise the state
is `insufficient_precision`. The file does not contain an exact millisecond or
byte p95. Spread-out histograms stay unresolved on purpose.

## Retention

A closed week is sealed once. The counters are then zeroed. The next week has
a new counter vector. There is no overlapping raw pool and no per-client row.
`reports-v3.sqlite3` keeps at most eight immutable weeks. Inserting the same
week again fails. The body is the protected JSON. v2 `reports.sqlite3` and
report schemas 1–4 are untouched and still validate on their own rules.

## Maintainer export

```text
python -m mnemion.product_telemetry.maintainer_v3 --state <absolute dir> --format json
python -m mnemion.product_telemetry.maintainer_v3 --state <absolute dir> --format csv
python -m mnemion.product_telemetry.maintainer_v3 --utility --format json
```

The summary says the export is not the local privacy page, that ticks are not
people, and that the noise is not an independent-user or causal interval.
`--utility` prints the model below. It does not read a fleet.

## Modelled utility

Assumption: every modelled installation contributes 2 or 7 ticks in one parity
week, and every tick lands in the same listed release or the same coarse OS.
A tick is not a person. A later week can miss these counts. "Usually published"
means the modelled tick count is at least `64 + 55`. A bucket is called usable
only when its modelled count is at least `110` as well.

| Installations | Reports each | Ticks | Denominator usually published | Majority bucket usable | Even 8-bucket split usable |
| --- | --- | --- | --- | --- | --- |
| 10 | 2 | 20 | no | no | no |
| 10 | 7 | 70 | no | no | no |
| 100 | 2 | 200 | yes | no | no |
| 100 | 7 | 700 | yes | yes | no |
| 1000 | 2 | 2000 | yes | yes | yes |
| 1000 | 7 | 7000 | yes | yes | yes |

At 10 installations the mechanism cannot support a product comparison. At 100,
a single cohort total and, with the dense 7-report model, a coarse majority
bucket can clear the noise. An even split across eight latency buckets cannot.
At 1000, both the majority and the even split clear this bar in the model.
None of those cells is a guaranteed observed count.

## Cohort arguments on the existing v2 path

Python activity, the browser activity and the desktop activity now pass coarse
platform, architecture and release-family values into the existing v2
`prepare` call. v2 still samples one view, so one packet still does not carry
the three values together. Unknown browser architecture is omitted and stays
`unobserved`. This wiring is not v3 and it does not enable collection.

## Still required before any activation

- Electron, browser and Python clients that encode and send v3, behind the
  same opt-out, company, GPC, metering and 7-per-week gates. Not started.
- Mounting `/v3/report` on a qualified host. `server.py` does not mount it.
- A versioned disclosure that says the collector sees bounded summaries and
  that provider retention was actually inspected. The current disclosure does
  not say that.
- Ingress, TLS, log and backup qualification for the operated path.
- The installed 2 MiB / 0.5% resource gates. This packet is 25 bytes in source.
  That is not an installed measurement. The failed full-app trials were not
  rerun.
- A dashboard, if one is wanted. The maintainer command is not that dashboard.
- Field 47 and the connector migration are a different change and were not
  touched here.
