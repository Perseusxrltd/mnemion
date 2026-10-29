# 29 October 2026 — gated v3 telemetry reference

V08 stays Building. This note records the corrected source candidate on
`grok/telemetry-aggregate-v3-20261029`, after Astra's review of `1e03707d`.
It does not qualify ingress, disclosure, installed resources, or a client
upload. The app version was not changed. The earlier 13-pass run remains the
check of that first commit. The run below is the check of this correction.

## What was checked

Pinned interpreter:
`/home/jorqu/.local/state/mnemion-release/2026-10-10/release-venv/bin/python`.

```text
python -m pytest tests/test_product_telemetry_v3.py -q --tb=short
16 passed in 10.73s
```

The first attempt in this correction failed one export assertion: a single
closed report groups both release cohorts, so the exported cohort list is
empty. The check now seals 100 release reports, exports that closed report
after the allowlist grows, and still reads slot 0 as `4.46.53` and the
unlisted slot as 1.

The file keeps the original codec, clipping, disabled-group, missing-sensor,
hostile-packet, whole-vector L1, integer `ln(3)`, stable-slot, suppression,
storage, v2, header, activity, utility and maintainer checks. It also checks
the report-local axis coin, admission without cross-report eviction, the
quantile counterexample, a supported high-volume bucket, an old report after
an allowlist change, the 32-release domain inside the store limits, and a
publication failure that is not sealed again. The same 32-release seal, run
again on this interpreter outside pytest, was 215,576 bytes: above 65,536 and
inside 786,432, with 33 published release cohorts.

`python -m mnemion.product_telemetry.maintainer_v3 --utility --format json`
prints the table in the
[v3 implementation note](../implementation/anonymous-product-telemetry-v3.md).
Each report chooses release or coarse OS with probability 1/2. At 10
installations neither 2 nor 7 modelled reports clears the lower side of that
split. At 100, two reports stay under the publish bar; the model frequency of
clearing 119 on one axis is 0.004361, and the publish flag stays no. Seven
reports clear a cohort total and a coarse majority bucket. At 1000, an even
8-bucket split can as well. Those are modelled products, not guaranteed counts.

On the same interpreter, one latency coordinate's envelope radius is 92. A sum
of six independent noises has radius 254, and a sum of 37 has radius 552.
The counterexample histogram is `insufficient_precision` for both percentiles.
A 20,000-tick spike is a 10–49 ms bucket bound on one cohort and
`insufficient_precision` on the six-cohort sum. Neither label is a percentile
confidence interval.

The browser activity test file was not executed. This clone has no
`studio/frontend/node_modules`, and this correction did not change frontend
wiring. No installed-app or native resource trial was repeated. No live
Perseus or Vercel probe was sent. Connectors and field 47 were not modified.

## Privacy-model change

Wire v2 still locally randomizes one category. The v3 candidate does not. The
reference collector adds a bounded summary into one week's counters and the
seal adds two-sided geometric noise. Epsilon at most `ln(3)` is for adding or
removing one input report from the published vector, including admission and
clipping. Admission does not evict a different report, so that change stays
inside L1 20. It is not a promise about the collector, the network, or a
person who sends several reports.

## Integration follow-up

Astra accepted the five mechanism corrections in direction. Pinned Python, same file:

```text
python -m pytest tests/test_product_telemetry_v3.py -q --tb=short
18 passed in 14.79s
```

The two new checks reject `unexpected_free_form_label` on `report_unit` and `weighting`, reject nine current or future failure weeks before insertion, and keep twelve successive closed-week failure notices inside the eight-week window. Repeating a valid week does not add a row. The clock advance drops notices that leave the window. That run drew no publication noise and stored no report body.

The desktop cohort helper no longer imports `package.json` as an ESM JSON module. Node 22.22.0 rejected the compiled import with `ERR_IMPORT_ATTRIBUTE_MISSING`, and this electron tsconfig emits the import without a `type` attribute. The helper reads the manifest beside `dist/` with `readFileSync`, the same shape already emitted for the other desktop JSON files. `scripts/test-telemetry-owner.mjs` imports `dist/telemetry-cohorts.js` and checks the release family. This Windows session did not install Node dependencies and did not run that compiled test. Astra's earlier Electron type-check and six browser activity checks are unchanged by this Python run. Collection stays off. V08 is not complete.
