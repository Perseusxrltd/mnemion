# Legacy Chroma vendor telemetry: unreleased source correction

**Recorded 23 October 2026.** The correction disables vendor product telemetry
for Mnemion's legacy Chroma storage clients. Source checks passed; release,
native-package and installed acceptance of this correction are not established.
It is **separate from frozen 4.46.3**, which remains unchanged. Mnemion's
[V08 product analytics](../implementation/anonymous-product-telemetry.md) remain
Planned and inactive, with no instrumentation or collector deployed.

## Baseline finding

A synthetic legacy save/read/delete check at **14:29:07 UTC** used Chroma
**0.6.3** and PostHog **7.67.0**. Vendor telemetry was enabled in the selected
Chroma settings. The operation reached **five SDK capture calls** and created
a persistent vendor identifier.

The capture boundary was replaced by a **no-send spy** that recorded calls
without forwarding them to the SDK or network. Five attempted capture calls
are not five transmissions.
This evidence does **not** establish any historical successful transmission or
its contents. The currently pinned SDK's incompatible capture signature is not
relied on to prevent disclosure, and suppressing its log messages is not a
privacy control. The original baseline remains preserved.

## Source correction

The shared legacy-client factory in `mnemion/chroma_client.py` selects a no-op
`ProductTelemetryClient`, sets `anonymized_telemetry=False`, and explicitly sets
both `chroma_product_telemetry_impl` and its older `chroma_telemetry_impl` alias.
The no-op discards events without invoking the vendor sender or reading its
identifier. Explicit settings prevent environment defaults from selecting the
vendor implementation for these clients.

All production Chroma constructors use this factory: the backend cache, CLI
repair, archive reconciliation and rollback. Legacy fixtures and benchmarks
use matching settings so reopening the same Chroma store does not introduce
conflicting singleton configuration. The old package-level telemetry logger
suppression is removed. These changes do not alter native-memory storage.

The correction does not delete an existing third-party identifier file or
change settings for other Chroma applications. It does not implement V08 or
change the consent and connection controls for configured sources, model
endpoints, memory services or updates in the [privacy policy](../service/privacy.md).

## Verification

The new regression runs a **fresh subprocess without pytest's implicit upstream
telemetry disable**. It sets environment values attempting to re-enable vendor
telemetry, replaces the vendor capture boundary with a recorder and blocks
network connections. Real synthetic local operations save, read, query, delete
and reopen the store. The result records:

- **Zero vendor capture calls.**
- **Zero network attempts.**
- **No new persistent vendor identifier.**
- Successful storage/query/deletion and an empty collection after reopening.

The focused selection passed **52 tests in 87.93 seconds**, covering this
regression, backends, conversation/general mining, legacy archives and MCP.
It reported **237 upstream Pydantic `instance.model_fields` deprecation
warnings**, with no failures. Ruff lint and format checks passed for all
**18 changed Python files**. These are source checks, not native or live-release
acceptance; no benchmark performance result is claimed.

Private originals `before.private.json` and `focused-checks.receipt.json` under
the dated `2026-10-23-legacy-vendor-telemetry` evidence directory retain the
observations and tested-file hashes. Vendor identifiers and raw payloads are
not published here. Existing requirement texts, counts, states and the future
telemetry acceptance contract are unchanged.
