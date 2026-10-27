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

## Release qualification follow-up

The existing [4.46.33 native run](https://github.com/Perseusxrltd/mnemion/actions/runs/40426432624)
reported the same Unicode-path fixture failure on Windows x64 and ARM64
(jobs `121935180712` and `121935180759`). Both original logs are retained.
The test sent UTF-8 JSON to Python's default Windows ANSI text stream, so
`private choice % # é` became a different directory. An actual Windows Python
3.13.11 round trip reproduced the CP1252 decoding error and verified UTF-8.
The fixture now explicitly sets `PYTHONIOENCODING=utf-8`; its non-ASCII path,
SQLite behavior and permission checks remain unchanged. The product telemetry
CLI already decodes bounded input bytes independently of that text-stream default.

On actual Windows x64, Node 25.2.1 and Python 3.13.11 passed all **40 storage
checks with no skips**, including the original Unicode path, opt-out, stale
authority, contention, hard-link and public-ACL cases. The unchanged native
permission helper was compiled locally with MSVC; cached JavaScript inputs
matched the unchanged runtime source. Only disposable fixture files were used
and their temporary staging directory was removed. This is component evidence,
not an installed release or Windows ARM64 acceptance receipt.

The [publication documentation push](https://github.com/Perseusxrltd/mnemion/actions/runs/40426293665)
also exposed a CI classification gap: known `-publication.json` and
`-artifacts.json` receipts were treated as unknown runtime inputs. The strict
versioned release-receipt rule now includes those two suffixes alongside
`-status.json`. Unknown variants, schemas, nested fixtures and runtime changes
retain full checks; releases and non-push events always do. **30 focused checks
passed**, including a real Git push comparison and the existing fail-closed
revision/rename cases. Reclassifying the original four-file documentation diff
returned `documentation_only`. Neither original workflow was cancelled or retried.

The private `release-qualification-followup.json` receipt has SHA-256
`1ee2e653c7f3afeb522c84a23154c526a46089c011adeeb731be41cdc1c08556`.
It binds the original failures, corrected checks and their exact inputs. The
previously qualified 57 MCP checks were not repeated for these isolated changes.

These source checks do not establish resource, provider/privacy or installed
acceptance. All 66 requirement texts and states remain unchanged; V08 stays
Building with collection/destination/route **false/null/null** and release CAs
empty. The **2 MiB / 0.5%** gates and prior failures remain binding.
