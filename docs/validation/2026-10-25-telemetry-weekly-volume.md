# Telemetry closed-week volume and report compatibility

**Source validation, 25 October 2026. V08 remains Building.** Production
collection is disabled, the destination and transport route remain unset, and
no completion notice has been sent. This batch follows the source frozen for
4.46.9; it is not included in that candidate.

The collector can now retain a coarse global volume range for a closed week
after at least 64 accepted contributions. For example, 700 reports produce
`{"minimum":512,"maximum_exclusive":1024}`. Detailed views still require
4,096 reports each and retain their original simultaneous confidence bounds,
noise and rare-value suppression. No exact total or suppressed-view residual
is added. Below 64 accepted reports, the whole week is discarded.

This gives operators a limited collection-volume signal when detailed
statistics are unavailable. It does not estimate people, installations,
retention or adoption. Reports are unauthenticated; a malicious sender can
inflate volume. The new threshold is not a distinct-person anonymity bound.
Packet privacy still protects one selected categorical value conditional on
its permitted view, not participation or a person's lifetime history.

## Format and retention

New closed reports use **report schema v2**, adding root `report_range`.
The original four-byte wire packet remains **v1**. The `server reports` command
also retains its **v1 envelope**; each item identifies its own report schema.

The private publisher accepts existing report-v1 records without rewriting
their stored bytes or inventing a volume range. Its database layout remains
unchanged. New reports must have exact reviewed fields, valid power-of-two
ranges and mutually possible global/per-view ranges. Closed weeks remain
immutable, with eight-week retention and the existing storage caps. There is
no live, filtering or comparison-query endpoint.

## Evidence

The focused selection passed **67 tests in 17.87 seconds**:

```sh
python -m pytest -q tests/test_product_telemetry_wire.py \
  tests/test_product_telemetry_publication.py \
  tests/test_product_telemetry_collector_server.py
```

It covers the existing exact packet-distribution/privacy checks, rejection of
private/free-text input, real TLS collector behavior and the clean minimal
runtime. Added checks cover zero/63/64/127/128/700/4,095-report windows, erased
accumulators, one publication at a week boundary, absent live/filter routes,
unchanged v1 database bodies, and rejection of malformed or inconsistent ranges.
No source behavior was enabled on an installed user app by these tests.

The retained maintainer log is
`2026-10-25-telemetry-weekly-volume/focused-tests.log`;
SHA-256 `8e66dfe1b290aa233f5baa42be46c1770f568f8f14d08be0b624d3b4405bb75f`.
The desktop TypeScript build also passed after the shared wire metadata changed.

## Remaining acceptance

This improvement does not qualify useful detailed statistics for a small
population. Their much higher sample requirements remain visible. Actual
production ingress/provider logging, retention and load qualification, client
resources, whole-wire limits and installed platform journeys still gate V08.
The current 2 MiB client RSS target is unchanged and remains unaccepted.

See the [delivery design](../implementation/anonymous-product-telemetry-delivery.md),
[collector guide](../implementation/anonymous-product-telemetry-collector.md),
and [complete V08 contract](../implementation/anonymous-product-telemetry.md).
