# Telemetry report-review selection defect — 26 October 2026

**Final source checks passed: 149 Python tests in 31.62 seconds, 113
browser-source checks and 41 native Node checks, without skips.** Electron and
frontend builds passed. Wire v2/report v3 now use a fixed manual body without
categorical measurements. These changes are excluded
from frozen 4.46.14 source `a5e574a9676ab724141b024d9ac1bb795ef1a688`. V08 remains
**Building**; production collection/destination/route remain **false/null/null**,
and all 66 requirement states are unchanged.

## Original evidence

An exact finite example showed that choosing which randomized packets to send
can invalidate categorical estimates. It was reproduced offline against source
`4509ba138fb9d5e73bcd5745de2c64e2b0ef8a70` at **07:28:30 UTC**.

The retained probe enumerated valid outcomes of the real
[wire v1 codec](https://github.com/Perseusxrltd/mnemion/blob/4509ba138fb9d5e73bcd5745de2c64e2b0ef8a70/mnemion/product_telemetry/wire.py) for the
`feature_family` view, then passed a selected subset to the real
[aggregate reader](https://github.com/Perseusxrltd/mnemion/blob/4509ba138fb9d5e73bcd5745de2c64e2b0ef8a70/mnemion/product_telemetry/reporting.py).

| Finite synthetic example | Result |
| --- | --- |
| Original category | `setup` |
| Offered valid reports | 12,480 |
| Selected reports | 4,160, exactly one third |
| Distribution of the selected subset | Exactly the valid distribution for `workspace` |
| Collector estimate for `workspace` | 1.0, interval **[0.865, 1.0]** |

Every selected packet belonged to the original valid multiset. No forged packet
was needed: conditioning inclusion on its bytes changed the distribution that
the estimator received. Wire v1 carries no review/selection mode, so the
aggregate reader treated the subset as ordinary independent reports. This is
constructed synthetic evidence, not observed user behavior: **zero network
requests, user data or production collection** were involved.

| Original evidence | SHA-256 |
| --- | --- |
| Finite-example probe | `70db755de61ac0c623efc96684856fd64f913afdb5a3f7ba6328d82d7949fcba` |
| Original selection result | `a8b88fbcdc2360105f7bbb2deb1ed6c1b374847a511d7f9ce74d305549090c04` |

## Implemented source correction

[Wire v2](../../mnemion/product_telemetry/wire-v2.json) distinguishes automatic
from reviewed reports while retaining the **four-byte body**, automatic
randomization and delivery budgets. Before inspection, manual preparation
selects the first permitted view and fixes coordinate `0` and flags `2`.
It uses no category or coin entropy and transmits no categorical measurement.
The body is fixed for the permitted groups; the decoder refuses reviewed
coordinates/signs outside that canonical form. Stored review validation also
rejects an altered first permitted view. Allowed flags are exactly `[0, 1, 2]`,
including automatic flags `0`/`1`. Legacy wire v1 is rejected because it cannot
distinguish selection modes.

The [collector accumulator](../../mnemion/product_telemetry/reporting.py) counts
reviewed packets only toward the existing coarse closed-week global volume
range. They contribute to neither categorical sums nor per-view counts,
thresholds or precision. No separate manual count or identity is published.
Thresholds remain **64 total reports per window** and **4,096 automatic reports
per detailed view**.

Report schema v3 declares `estimation_population: "automatic_reports_only"`
and `reviewed_report_use: "coarse_global_volume_only"`, with packet-independent
inclusion and correctly marked, independently randomized automatic reports as
explicit assumptions. This is not an estimate of all users or activity and is
not sender authentication. The [publisher](../../mnemion/product_telemetry/publication.py)
still reads immutable aggregate report v1/v2 documents without rewriting them;
that compatibility does not admit old wire packets.

Exact previews expose `report_selection`, `aggregation` and
`privacy_bound_scope: "fixed_body_for_permitted_groups"` for reviewed packets.
Both `per_report_privacy_loss` and `randomization_privacy_loss` are null for
manual review. The app explains that the fixed body contains no categorical
measurement and contributes only to volume. The `ln(3)` bound remains scoped
to automatic randomization and packet-independent inclusion, not human review.

## Final source validation

The final checks cover constant manual preparation without entropy, rejected
noncanonical coordinates/signs and altered first views, unchanged automatic
estimates and precision, and immutable aggregate v1/v2 readers. Exhaustive
Python/TypeScript parity, actual Python/Node private SQLite review handoff and
real standalone/systemd TLS acceptance/refusal checks passed. These are source
and component results; no renderer benchmark or installed-platform journey ran
for this batch.

| Final evidence | SHA-256 |
| --- | --- |
| Canonical check summary binding logs and builds | `887513499f6287c92e571ac7773954aac8e49fa4d1f3287a577fd3ce3d8c26ab` |
| Python checks | `6490ed029b7191dfade4c0f08157fdfac585623e0f077a9b8238a44dd7d3e257` |
| Browser-source checks | `b308f749e7ac8d6d7443ee2517b63df3e407c6796a47e0dc18da398e5ce308c2` |
| Native Node checks | `3733a9f4df76c17a25b59be5f63a2f590f5173c38abd8de5e74030c5ca0b97db` |

## Windows ARM runtime-clock fixture follow-up

The original 4.46.14
[Windows ARM job 121453524412](https://github.com/Perseusxrltd/mnemion/actions/runs/40286600426/job/121453524412)
failed when the delivery fixture called `ctypes.CDLL(request['native_clock'])`
in x64 Python with the ARM64 Node helper, producing **WinError 193**. The original
log remains preserved. The supported Windows ARM desktop uses an x64 Python
engine; the test must respect that separate runtime architecture.

The [delivery fixture](../../studio/electron/scripts/test-telemetry-delivery.mjs)
now uses Python's normal runtime-clock loader, including its supported direct
OS reader, instead of injecting the Node binary. Product runtime code is
unchanged. The local delivery module passed **17 checks, zero failures/skips,
in 14.528 seconds**, with exit status 0. This overlaps the earlier selections;
it is not an additional all-platform total. Actual Windows ARM qualification
remains pending the 4.46.15 native pipeline.

| Follow-up evidence | SHA-256 |
| --- | --- |
| Original Windows ARM job log | `c95d08c36d95ccf51efb09e70e217bf3594842227c64780d3df29cd116bbd23f` |
| Local normal-clock delivery checks | `794c19893406de9f0cf28fd5edb312b02d6aadfed12b1a0ca65037d4f63fc3d8` |
| Local command exit receipt | `2effa7be8c992d232d04665d28f1337e17654b196fd7b8efef3e45daf68b46a8` |

## Retained intermediate checks

The initial Python selection retained **145 passes and two failures**: its
standalone/systemd TLS fixtures still sent literal wire v1 and expected success.
After correction, those **two real TLS cases passed in 5.90 seconds**, checking
v2 automatic/reviewed acceptance and v1 rejection. That intermediate run was a
targeted correction; the later final full selection is recorded above.

All **112 browser-source checks** and **40 native wire/delivery/TLS checks**
passed, without skips. The native Node selection includes exhaustive
Python/TypeScript parity for both selection modes and actual private SQLite
review handoff. Electron and frontend builds passed. These results cover the
intermediate marker-only implementation, before manual categorical bits were
removed. They remain historical evidence, separate from the final canonical
checks above.

| Scoped evidence | SHA-256 |
| --- | --- |
| Intermediate source-check summary | `4a51b24ed6fb785f14880bf20bed945cbdc72b29fa6567995d31dbf068d79f44` |
| Initial Python result, including two failures | `185d9095ece96ab85a8dc7a9deab3448e5d2216bb9e478630313d2951b45d293` |
| Corrected TLS cases | `7191500424871a9c851f771989e8d4d76e6237de909271fb7045e7cc193c6283` |
| Browser-source checks | `1d0057a60ed05ec23eb725ace01e81286e31ebd61ae268ad099fcae8ef5d852a` |
| Native Node checks | `085873c4119f81b08c7cb962015b85e77d78b1bb603918d386e114b02b9a000b` |

The strengthened manual body removes the categorical measurement entirely.
It still does not establish a general interactive privacy guarantee: arbitrary
human inclusion, policy-group choices and participation are outside the
automatic randomizer's conditional bound. Four bytes and a selection marker
establish neither participation nor network anonymity.
Interactive privacy, utility and the unchanged resource gates remain open.
