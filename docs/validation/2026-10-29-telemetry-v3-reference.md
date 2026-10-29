# 29 October 2026 — gated v3 telemetry reference

V08 stays Building. This note records a source candidate on
`grok/telemetry-aggregate-v3-20261029`. It does not qualify ingress, disclosure,
installed resources, or a client upload. The app version was not changed.

## What was checked

Pinned interpreter:
`/home/jorqu/.local/state/mnemion-release/2026-10-10/release-venv/bin/python`.

```text
python -m pytest tests/test_product_telemetry_v3.py -q --tb=short
13 passed in 7.40s
```

The file checks the 25-byte codec, clipping, disabled groups, missing sensors,
hostile packets, the L1 of one report, the integer `ln(3)` bound, stable
release slot 0 for `4.46.53`, noisy suppression without a one-cohort complement,
bucket-bound quantiles, immutable eight-week storage, absence of the raw packet,
v2 decode/schema/disclosure, a request header that cannot select the test RNG,
Python activity cohort arguments, the utility table and the maintainer export.

`python -m mnemion.product_telemetry.maintainer_v3 --utility --format json`
printed the table in the
[v3 implementation note](../implementation/anonymous-product-telemetry-v3.md).
At 10 installations neither 2 nor 7 modelled reports clears the noise. At 100,
the denominator can, and a majority bucket can only in the 7-report model. At
1000, an even 8-bucket split can as well. Those are modelled products, not
guaranteed counts.

The browser activity test file was not executed. This clone has no
`studio/frontend/node_modules`, so the existing TypeScript test runner could
not start. The new browser helper did typecheck under a global `tsc` apart
from Node types, which the electron project normally supplies and which are
not installed here. Desktop `process` use matches the surrounding electron
code. That is not a browser run.

The failed full-app resource trials were not repeated. No live Perseus or
Vercel probe was sent. Connectors and field 47 were not modified.

## Privacy-model change

Wire v2 still locally randomizes one category. The v3 candidate does not. The
reference collector adds a bounded summary into one week's counters and the
seal adds two-sided geometric noise. Epsilon at most `ln(3)` is for adding or
removing one report from the published vector, including the denominator and
the cohort partition. It is not a promise about the collector, the network, or
a person who sends several reports.
