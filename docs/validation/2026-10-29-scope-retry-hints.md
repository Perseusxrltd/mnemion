# Search retry hints and installer download limit — 29 October 2026

Source 4.46.48 marks HTTP 409 `scope_changed` as retryable in the Python and
TypeScript SDK errors. The MCP response uses the Python hint. A caller can issue
a fresh global search to resolve its current permitted spaces; this adds no
automatic request replay. Other 409 conflicts, including `generation_changed`
and `version_conflict`, retain their existing hints and handling.

The prepared source binds 1,023 inputs. Its scoped changes are the two SDKs,
their two test files and the installer verifier. Preparation updates 13 version
boundaries and the generated coverage inventory's matching TypeScript source
hash; the inventory's workflow classifications are unchanged.

## Reproduction and correction

The original Python run reproduced two product failures: the SDK and actual
HTTP/MCP response both returned `retryable: false` for the new scope conflict.
It also contained one fixture error that expected an HTTP 409 write refusal to
be classified as `unknown`; the correct existing outcome is `rejected`.
The original receipts retain all three failures. The corrected fixture checks
both 409 `rejected` and 503 `unknown`, and preserves the no-replay write fence.

The original TypeScript run separately reproduced the false retry hint. Its
build passed and its new assertion failed. Both original failed runs remain
separate from the successful corrected checks.

The corrected run completed at **01:19:26 UTC**:

| Check | Result |
| --- | --- |
| Python SDK, real HTTP/MCP, agent controls and busy handling | 46 passed, no failures or skips |
| Compiled TypeScript SDK | 23 passed, no failures or skips |
| Ruff on the changed Python source and test | Passed |

The real PostgreSQL fixture expands readable spaces during query embedding.
The first MCP search receives `scope_changed` with the fresh-search hint and no
new-space name; the next explicit search succeeds. SDK fixtures verify one
request per 409 despite a configured retry count. Agent-control fixtures verify
that an unprotected write is sent once and retains `retryable: false` for both
tested refusal/outcome cases.

This qualifies error handling, not live latency or the cause of the field
incident. The [four-client baseline](2026-10-29-mcp-field-sessions.md) and
[field acceptance plan](../implementation/multi-agent-field-readiness.md)
retain the remaining deployed search work.

## Installer limit

The existing [installer verifier](../../studio/electron/scripts/verify-installer.mjs)
now rejects a packaged download larger than **419,430,400 bytes (400 MiB)**
and records that budget beside actual installer sizes. The existing lower bound,
required native resources, signatures, checksums and platform-specific
verification remain. No packaged capability is removed.

Local JavaScript syntax validation passed. The new limit still requires the
normal native release matrix on this source; this is not a claim that 4.46.48
artifacts have been built or published. The [footprint plan](../implementation/installer-footprint.md)
retains the original report, measured artifacts and further reduction work.

All 66 requirement states are unchanged. Telemetry remains Building with
production collection disabled; the separate systemd crash result does not
qualify full telemetry completion.
