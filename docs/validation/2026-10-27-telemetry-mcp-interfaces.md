# Local MCP privacy schema and coverage — 27 October 2026

This source follow-up is based on `aba7322aca0ce901df6f9ac5ad2916c7134ec309`.
It aligns the legacy local privacy-tool schema with its existing backend controls
and includes both MCP interfaces in the shipped coverage report's independent
source inspection. It adds no telemetry owner or production collection.

## Privacy arguments

The [legacy `mnemion_telemetry` schema](../../mnemion/mcp_server.py) now advertises
all nine existing offline actions: `status`, `schema`, `preview`, `configure`,
`review_status`, `review_mode`, `inspect_report`, `approve_report` and
`discard_report`. It exposes `connection_mode`, `expected_review_token` and
`mode`, and permits disclosure version `0` under the existing policy rules.
Version zero does not acknowledge unseen disclosure.

Privacy arguments now reach strict backend validation unchanged. Unknown fields
are not silently discarded, and numeric privacy inputs are not coerced by the
generic legacy compatibility path. Non-object privacy arguments return bounded
JSON-RPC error **-32602**. Other legacy memory-tool arguments retain their
existing filtering and numeric compatibility behavior. Privacy controls remain
local/offline, create no usage observation and do not themselves send reports.

## Visible source coverage

The [coverage generator](../../deploy/telemetry_actions.py) statically reads the
maintained gateway's tool decorators and invocation aliases, plus the legacy
`TOOLS` keys, without importing or executing either server. Unsupported changed
registration syntax requires review. Independent MCP-map tests already existed;
this change brings the source bindings and missing-action visibility into the
shipped coverage report.

There are now **seven independently inspected interfaces** and **six checked
owner categories**. Both MCP interfaces share `local_stdio`; the other five are
the control contract, native actions, SDK methods, legacy UI and desktop preload.
Counts remain **632 actions/fixed variants: 360 mapped, 265 excluded, seven
delegated and zero unmeasured**. Workflow categories remain **94 total, 93
mapped**, with `update.verify` deliberately unmeasured separately from its
download/staging cycle. Other owners still use reviewed source-route maps;
declarations do not prove every call site or installed runtime.

## Evidence and limits

The original regression selection first stopped during collection because its
service environment lacked `chromadb`; **no tests executed**. That environment
failure is retained. The qualified environment then reproduced **18 failures**
against the original source. The corrected focused selection passed **46 checks
in 9.94 test seconds** (11.948 seconds wall time).

The private `2026-10-27-telemetry-mcp-interfaces` evidence set retains both original
attempts and the passing logs. `original-qualified-environment.json` has SHA-256
`eee6810f9b6c72d7b80ba2baacaa18046cb9c793cffe6dd78e689c7f0e0cb545`;
`focused-checks.json` has SHA-256
`6ec5dcad56fd477dd6fb13f85a5a710666fdac4e51d8853a8598665adc3ad6a3`.
`compatibility-checks.json` and its log record **11 existing TestHandleRequest
and Open Brain compatibility checks passed** in **19.19 test seconds**
(21.44 seconds wall time), with 11 existing third-party Chroma/Pydantic
deprecation warnings. Together with the focused selection, **57 distinct checks
passed**; no passing selection was repeated.

These source checks do not establish resource, provider/privacy or installed
acceptance. All 66 requirement texts and states remain unchanged; V08 stays
Building with collection/destination/route **false/null/null** and release CAs
empty. The **2 MiB / 0.5%** gates and prior failures remain binding.
