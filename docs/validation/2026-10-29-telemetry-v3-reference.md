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

## Served collector and private HTML

The original `18 passed in 14.79s` above was not re-run. Astra's compiled Electron owner test, 9 passes including the emitted-module import, was not re-run. Pinned interpreter `/home/jorqu/.local/state/mnemion-release/2026-10-10/release-venv/bin/python`:

```text
python -m pytest tests/test_product_telemetry_v3_operator.py tests/test_product_telemetry_v3.py::test_maintainer_export_is_validated_and_is_not_a_privacy_page tests/test_product_telemetry_v3.py::test_closed_report_keeps_its_domain_when_the_allowlist_grows tests/test_product_telemetry_collector_server.py::test_only_fixed_route_flags_reach_aggregate_processing -q --tb=line
9 passed in 9.46s
```

That run is local. It checks the explicit v3 TLS listener against its own packet, a malformed packet and the legacy route, empty logs, and the separate sqlite file. The default serve mode still answers `/v1/report` and does not create `reports-v3.sqlite3`. A quiet boundary wake drops in-memory failure notices outside the eight closed weeks. JSON and CSV export still read the sealed store. HTML shows a negative noisy denominator, `bucket_bounds` and `insufficient_precision`, and escapes a `</script>` payload. Ordered bucket edges and the release and OS ids come from the closed report. Category names do not: schema 2 stores `{id, kind}` for a category metric and the export reads the label from the current wire-v3 catalog. That run does not show that a future category rename would stay on an old report. The first export assertion in this session failed because it expected the CSV body to contain `publication_failed`; the passing check uses the summary week column. That failure is retained. A missing export directory does not create a database, and the rejected path is not printed. No internet collector, installed-resource trial, host change, or version bump. V08 stays Building.

## Corrupt store, category labels, and the page trend

The `9 passed in 9.46s` run above was not repeated. The same pinned interpreter ran only the new operator and page checks:

```text
python -m pytest tests/test_product_telemetry_v3_operator.py::test_corrupt_or_locked_export_stays_a_fixed_error tests/test_product_telemetry_v3_operator.py::test_v3_serve_rejects_a_bad_store_without_replacing_it tests/test_product_telemetry_v3_operator.py::test_category_names_follow_the_live_catalog tests/test_product_telemetry_v3_operator.py::test_remainder_trend_uses_the_same_member_set_and_week_positions -q --tb=short
4 passed in 7.98s
```

Pinned Ruff on `server.py`, `maintainer_v3.py`, `collector_v3.py`, and `tests/test_product_telemetry_v3_operator.py` reported `4 files already formatted` and `All checks passed!`. A corrupt or locked `reports-v3.sqlite3` stays in place. Export returns `telemetry_v3_export_rejected`. Explicit v3 serve returns `telemetry_collector_configuration_invalid`. The category check renames the live outcome label and leaves the stored legend at `{id, kind}`. The page check keeps a remainder trend on one member set at real week positions, and it keeps `unlisted` selected when the next week reuses that numeric slot for `4.46.54`. V08 stays Building.

## Release cohort preparation

The operator runs above were not repeated. `wire-v3.json` still lists only `4.46.53`. Pinned Ruff format and lint on `deploy/release_automation.py`, `service_tests/test_release_automation.py`, and `tests/test_product_telemetry_v3.py` were clean. The same pinned interpreter:

```text
python -m pytest service_tests/test_release_automation.py::test_version_preparation_preserves_unrelated_pins_and_is_repeatable service_tests/test_release_automation.py::test_prepare_adds_current_and_target_release_cohorts service_tests/test_release_automation.py::test_prepare_retains_at_most_32_release_cohorts service_tests/test_release_automation.py::test_prepare_rejects_invalid_release_cohorts_without_writing -q --tb=short
5 passed in 7.06s
```

```text
python -m pytest tests/test_product_telemetry_v3.py::test_release_coordinates_keep_their_meaning_and_unknown_values_collapse tests/test_product_telemetry_v3.py::test_suppression_uses_noisy_output_and_does_not_isolate_one_cohort tests/test_product_telemetry_v3.py::test_quantiles_are_bucket_bounds_or_insufficient_precision tests/test_product_telemetry_v3.py::test_closed_report_keeps_its_domain_when_the_allowlist_grows -q --tb=short
4 passed in 12.59s
```

Preparation adds the current source release and the target, keeps at most 32 contiguous slots, and does not write when the coordinate or catalog is invalid. A fixed one-release catalog fixture holds the known `4.46.53`, unknown `4.46.54`, and unlisted index 1 checks. V08 stays Building.

## Integrated release-catalog check

At 21:59 UTC on 29 October, Astra checked the combined source after normal
preparation of 4.46.55 (`4cf4b400`). The release catalog contains 4.46.53,
4.46.54 and 4.46.55. Using the existing pinned release interpreter:

```text
python -m pytest tests/test_product_telemetry_v3.py tests/test_product_telemetry_v3_operator.py -q --tb=short
31 passed in 11.07s
```

This qualifies the combined codec, aggregation, closed-report compatibility and
private operator checks with that expanded catalog. It does not qualify an
installed client, production collector, provider or resource overhead. Original
receipt: `automation/astra-grok/telemetry-release55/prepared-cohort-checks-original.json`
in the private completion evidence; no failed receipt was replaced.
