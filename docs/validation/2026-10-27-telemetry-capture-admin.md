# Capture administration, replay receipts and grant binding — 27 October 2026

Reviewed source is based on `626e25ea3e8084e788b5564db19f92663f29bf7d`.
This batch is selected for **4.46.36** because it corrects an ordinary capture
authorization bug as well as telemetry coverage. Publication follows the normal
release gates. **V08 remains Building**; production collection/destination/route
remain **false/null/null**, with release certificate authorities empty.

## Grant collision and correction

Two enrollments can use the same grant ID for different sources. Their source
locks are distinct: after one request observes no grant, a competing request can
commit that ID before the first request's `INSERT ... ON CONFLICT DO NOTHING`.
The earlier implementation returned the winning row without checking that it
belonged to the requested source. A retained reproduction over two interleaved
real PostgreSQL transactions failed with `DID NOT RAISE ServiceError`.

The service now checks the actual post-insert source, device key, policy version
and revocation state against the approved request. An incompatible winner raises
the existing `capture_grant_immutable` conflict; the winning authorization is
preserved. A valid repeated enrollment still retains its original policy.

## Actual app actions and receipt ownership

The Capture administration page's **Approve policy change** and **Confirm
revocation** buttons previously called the generic SDK request method. They now
use `changeCapturePolicy` and `revokeCaptureGrant`, through the existing disclosed
Studio measurement wrapper on desktop and web. Their reviewed body, error and
result remain with the caller. IDs are encoded as path components, and an
unconfirmed write is not automatically retried.

Five capture boundaries return the existing request-local `new`/`replayed`
metadata: source configuration/revocation, device authorization/revocation and
policy changes. The control maps require a fresh receipt. The service is not a
telemetry owner. Grant insertion uses the actual insert result, and revocation
reads current state again after taking its source lock. Repeated changes,
unchanged setup, cached results, read-only inspections and legacy replies do not
become fresh capture uses.

Qualification also caught the agent command layer discarding valid response
metadata when the request had no `Idempotency-Key`. The five fresh CLI cases
therefore initially recorded zero observations. The command layer now preserves
the fixed response metadata independently of retry policy; a response header
cannot authorize another attempt. The live API-to-agent policy transition test
checks both the new and replayed results.

Generic SDK consumers and HTTP requests acquire no measurement owner. Automatic
reviews/history reads remain excluded. Device enrollment and recovery's transport
steps retain their existing enclosing native source/recovery boundaries. No
policy text, path, source, grant, device, review token or response content is
copied into telemetry.

## Qualification

The [machine-readable result](2026-10-27-telemetry-capture-admin.json) records:

- **106 distinct Python tests qualified.** The initial 94-test selection had
  89 passes and five CLI failures. After the metadata correction, 44 control
  tests passed, including all five failures and the live API-to-agent case.
  The selections overlap by 32 tests; 62 unchanged initial checks were not run
  again. Collection of test IDs established the distinct total without executing
  the tests again.
- **22 SDK and 49 Studio/policy source tests passed**, without Node skips.
  They cover fresh/replayed/missing metadata, preserved private requests,
  opt-out during a pending reply and unchanged retry authorization.
- **SDK, frontend and Electron builds passed.** The first frontend build exposed
  an unresolved type import from the shared declaration directory. Resolving
  the already-built SDK declaration by relative path restored policy typing.
  Passing Python and SDK tests were not repeated for that declaration fix.
- **29 recorded source inputs matched.** The original grant-race failure, CLI
  failures and frontend build failure remain retained with their corrections.
  Disclosure, route, metric catalog and both wire contracts are byte-unchanged.

The inventory still has **94 mapped categories**. Its **636 declared rows** are
**364 mapped, 265 excluded and seven delegated**, with zero declared unmeasured
rows. These are source declarations, not complete runtime or installed coverage.

Private qualification SHA-256:
`6ac7433eee502d1048a091a541ceabc7a9865eb167926dad668912eabad484c9`.

This qualification uses isolated PostgreSQL and source-level client fixtures;
it does not establish final installed desktop/browser journeys, outbound ingress
privacy or resource budgets. No new resource experiment or model call was made.
The [acceptance ledger](2026-10-27-telemetry-acceptance-ledger.md) retains full
runtime, native/web, wire, resource, provider and aggregate requirements. All
[66 product requirements](../PRODUCT_REQUIREMENTS.md) remain retained.
