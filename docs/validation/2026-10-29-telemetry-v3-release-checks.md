# V3 client release checks — 29 October 2026

Actual Grok Build implemented this batch on combined source `d36d0a2d`;
Astra reviewed the changes and completed the evidence record. Collection remains
unavailable, with no production destination or route. These are local source
checks, not installed-platform, provider or resource acceptance.

Current policy fixtures now acknowledge the current disclosure. Legacy wire v2
codec tests read their original source contract, while the active packaged
resource remains v3. The existing Electron test command also runs the shared
27-case v3 parity check. The installed-app probe verifies the exact 25-byte
synthetic example, its version and privacy labels, while retaining all default,
consent, opt-out, app/agent, review, refresh and no-attempt assertions.

## Original failures and corrected results

The existing pinned Python environment and Node 22 were used with existing
package dependencies. No dependencies or models were downloaded for these checks.

- Python policy/ownership selection: **328 passed, two failed in 97.10s**. Both
  MCP review fixtures still used `/v1/report` and expected four bytes. After
  correcting the fixtures to `/v3/report`, 25 bytes and schema 3, the two cases
  alone **passed in 10.12s**. Local-stdio-only approval, CAS and opt-out assertions
  remain. The 328 passing cases were not repeated.
- Electron policy, shared store and legacy codec selection: **67 passed, zero
  failed, two Windows-only skips** on Linux. The normal Electron build, including
  the real native helper, passed. These checks were not repeated.
- Cross-language v3 parity: **27 cases passed**. The fixed and expanded release
  catalog cases remain part of that check; it was not repeated for documentation.
- Browser policy selection: **33 passed, one failed**. The nominal queued-send
  fixture lacked an OS value, so the new sender correctly refused it. With a
  known platform supplied, all three ready/opt-out/page-exit cases **passed in
  7.397s**. The other passing cases were not repeated.
- Frontend build: the first attempt read outdated generated SDK declarations.
  Rebuilding the current SDK resolved those declarations and exposed three
  missing string callback annotations in capture-policy form processing. Explicit
  string annotations and equivalent empty-string filtering preserve that form's
  behavior. The complete frontend typecheck and Vite build then **passed in
  24.47s**. Both earlier failed build outputs remain retained.
- The corrected MCP test run passed while its formatting check still failed.
  Formatting was corrected and checked separately. Astra formatted the remaining
  changed Python fixtures and ran Ruff before committing; no behavior test was
  repeated for line wrapping.

Original job outputs and complete corrected logs remain under
`automation/astra-grok/telemetry-client/combined-checks/` and `combined-finish/`
in private completion evidence. The two bounded implementation jobs reached
request limits; neither limit is a test pass. Astra inspected their terminal
state before completing the review and commit.

The separate [expanded release-catalog check](2026-10-29-telemetry-v3-reference.md#integrated-release-catalog-check)
passed 31 combined collector/codec/operator cases after preparation of 4.46.55.
The normal release matrix and actual app measurement remain required. V08 stays
Building, all 66 requirements remain, and the 2 MiB / 0.5% gates are unchanged.
