# Product telemetry delivery components — V08

**Unreleased source checkpoint, 24 October 2026; V08 remains Building.** The
[full contract](anonymous-product-telemetry.md) and
[local catalog/ownership](anonymous-product-telemetry-catalog.md) retain their
scope. Python/TypeScript packet encoders, a volatile weekly accumulator, an
ASGI ingress adapter and a private closed-week publisher now exist in source.
**There is no sender, persistent shared
privacy/wire budget, installed integration, qualified ingress or production
activation.** The disclosure remains `collection_available: false` with
`destination: null`. Source and synthetic utility evidence is recorded in the
[delivery validation](../validation/2026-10-24-telemetry-delivery.md).

## One randomized category per report

The [version 1 format](../../mnemion/product_telemetry/wire-v1.json) defines
**23 views, 280 category values and 400 padded Hadamard coordinates**. The views
cover feature family/operation, invocation surface, outcome/reason, fixed metric
buckets and separate coarse platform, architecture and release-family cohorts.
They do not form a joined device profile.

The [Python](../../mnemion/product_telemetry/wire.py) and
[TypeScript](../../studio/electron/telemetry-wire.ts) encoders:

1. Select one view using fixed weights among permitted metric groups, independently
   of measurement values. They do not send all 23 views together.
2. Sample one category using the already bounded local cell counts. Missing
   sensors use `unobserved`, not a fabricated zero. Only reviewed cohort enums
   are accepted.
3. Choose a random Hadamard coordinate, retain its true sign with probability
   **3/4**, and flip it with probability **1/4**.

The result is exactly **four body bytes**:

| Byte | Meaning |
| --- | --- |
| 0 | Format version, currently `1` |
| 1 | Chosen view index |
| 2 | Random coordinate within that view's padded domain |
| 3 | Randomized positive-sign flag, `0` or `1` |

For example, `01 00 07 00` is a valid randomized body. Its component preview
identifies `feature_family`, coordinate `7`, sign `-1` and four body bytes; it
does not recover a true category. This is not an actual outgoing app request.
HTTP headers, framing, TLS and other transport traffic are additional bytes and
remain unqualified. App/native privacy preview still reports no outbound body.

`prepare` accepts only bounded `(cell, count)` pairs and reviewed cohort enums.
It does **not** read policy or enforce an attempt budget. Its future caller must
obtain a current policy-fenced snapshot and reserve the shared privacy/wire
budget before attempting delivery. Current `schema` exposes `transport_catalog`
with `transport_available: false`; discovery does not activate transport.

## What the privacy bound covers

For a fixed permitted view and coordinate, a randomized sign has probability
`3/4` or `1/4` under any possible category. The maximum likelihood ratio is
therefore `3`, giving **per-report local differential privacy ε = ln(3)** for
the sampled categorical value, conditional on that permitted view.

This is **not** participation, policy-choice, lifetime or network anonymity.
The chosen view is visible, permission groups affect view selection, and repeated
reports compose privacy loss. The packet contains no category label, local count,
stable identifier, generation token, credential or event timestamp, but absence
of these fields alone does not establish anonymity. Confidence and utility also
assume independent randomization by conforming senders; the source provides no
authenticated-contributor or poisoning-resistance guarantee.

The JSON's budget entries are **proposals, not enforced controls**:

| Proposed bound | Current status |
| --- | --- |
| At least 86,400 seconds between attempts | No persistent shared attempt state or scheduler |
| At most seven attempts per rolling week | Not enforced across processes, restarts or choice changes |
| Conditional weekly bound `7 × ln(3)` | Only follows if the proposed attempt bound is enforced; not a lifetime/person guarantee |
| Reserve 65,536 wire bytes per attempt | No sender or measured transport reservation yet |

Existing local cell/contribution limits, which clear on explicit choice, are not
this missing privacy budget. The contract's opt-out fencing, final-send
cancellation and resource/bandwidth ceilings remain unchanged.

## Fixed closed-week output

[AggregateWindow](../../mnemion/product_telemetry/reporting.py) retains signed
coordinate sums and per-view counts, not raw reports or client rows. Its **400
signed coordinates plus 23 counts occupy 3,384 array bytes**; that excludes Python
objects, server/TLS overhead and published output. The source bounds a window to
ten million accepted reports. A window seals once in memory and clears its arrays;
live accumulation is not persisted across restarts. The standard publisher makes
completed weekly documents immutable.

The [ASGI adapter](../../mnemion/product_telemetry/collector.py) accepts only the
fixed four-byte frame at `POST /v1/report`, with bounded body assembly and a
five-second receive deadline. It does not inspect or retain authorization,
cookie, user-agent, referrer or peer fields. It exposes no live statistics or
arbitrary query/filter endpoint. These adapter properties do not qualify the
actual server, TLS terminator, proxy or provider: transport metadata and logs
still require evidence through the complete deployed path.

Weeks are server-owned, fixed Monday-to-Monday windows. Only a closed window is
passed to a publisher callback. Each view needs **at least 4,096 reports**, and
output uses power-of-two count ranges such as `[4096, 8192)`, never a distinct-user
count. Below the threshold the view is `insufficient_reports`; a rare/noisy cell
whose confidence interval includes zero is `insufficient_precision`, with no
published point estimate or residual. Inconsistent estimates suppress the view.
Published fractions describe sampled categories, not unique users or total
global feature usage.

Clock rollback and shutdown discard volatile state; publisher failure drops the
closed result rather than creating a raw-request backlog. The standard
[ReportStore](../../mnemion/product_telemetry/publication.py) validates complete
closed-week JSON documents and stores them in a private SQLite database, capped
at **eight weekly rows, 64 KiB per report and 1 MiB for the database**. Inserts
cannot replace an existing week's report; there is no upsert or partial
publication. Startup, reads and publication prune expired windows. The active
collector also invokes pruning at week boundaries when no new result qualifies.
The [source checks](../validation/2026-10-24-telemetry-delivery.md) now include
publisher tests and a **12-check actual plain-loopback HTTP journey** with
4,096 Python-encoded reports and one Node-encoded report. That isolated journey
verified immutable output, expiry without another qualifying window, empty logs
and graceful erasure/cleanup. It qualifies neither a product sender nor TLS,
provider logging, deployed restart behavior or retention of backup copies. The
publisher does not provide a public report route or configure a collection
destination. The final focused Python rerun after the test-only lint correction
passed **47 tests in 4.52 seconds**.

## Component resource diagnostic

An actual Linux headless-app probe after `client-ready`, using Electron 44.9.3
and Node 24.22.0, completed **32 encodings of full 512-cell synthetic queues**.
It recorded **11.784 ms elapsed, 19.804 ms process CPU and 126,328 additional
retained JavaScript heap bytes**. Process CPU can include concurrent work and
cannot be attributed solely to the codec. Net RSS fell **405,504 bytes**; treat
that as runtime/GC variation, not memory savings or evidence of zero overhead.
The probe made no sender, network, production-memory or model calls.

This is a component diagnostic, not whole-app or all-platform resource
acceptance. The earlier cold-memory gaps and the unchanged **2 MiB added RSS /
0.5% of one core** limits remain open; this probe does not replace them. The
[validation report](../validation/2026-10-24-telemetry-delivery.md) records its
original evidence; the final Python selection and frontend build passed.

## Material usefulness limit

The conservative simultaneous interval half-width at **4,096 reports per view is
13.495 percentage points**. This threshold is per view, not total reports:
with all groups permitted, the fine-feature view receives weight `16/256`.
The [synthetic study](../validation/2026-10-24-telemetry-delivery.md) covered
18 cases with 96 trials each. Two cases had **95/96** simultaneous coverage;
the other 16 had **96/96**. These are finite simulations, not a 100% guarantee.

Rare fine-grained features remain mostly unavailable even at **65,536 reports
per view**. Small deployments at the proposed cadence will not provide precise
fine-grained statistics. Missing or imprecise output must remain unavailable,
not be presented as zero usage or confident small-population estimates.

The remaining work includes persistent shared budgets, installed policy/producer
integration, sender cancellation and retry behavior, real transport/log privacy,
publisher/deployment retention qualification, resource/wire measurements, utility and attack
qualification, and all six native targets plus web. No V08 requirement is closed
by this component checkpoint.

## Primary references

- [Acharya, Sun and Zhang, *Hadamard Response*](https://arxiv.org/abs/1802.04705):
  primary background for Hadamard-based local distribution estimation. This
  component's exact support/ratio checks do not inherit every claim of the paper.
- [NIST SP 800-226](https://csrc.nist.gov/pubs/sp/800/226/final): evaluating privacy
  units, composition and practical differential-privacy hazards.
- [RFC 6973](https://www.rfc-editor.org/rfc/rfc6973.html): protocol privacy and
  metadata considerations beyond an application payload.
