# Busy inference fallback validation — 2026-10-12

Version **4.1.2** is published for all six desktop targets. The
[publication record](2026-10-12-busy-fallback-release.md) covers the subsequent
native gates, artifact/signature verification and public delivery checks.

Search and context requests can explicitly choose `on_inference_busy: "lexical"`.
The default preserves the retryable `503 inference_busy` response and retry
hint. A busy generation switches the whole request to keyword retrieval, with
`inference_busy_lexical_only` in its warnings. Context uses a consistently labeled
UTF-8 byte budget, including when token counting becomes busy after retrieval.

Local validation passed:

- 77 distinct tests across inference limits, retrieval, reindexing, HTTP, Python
  clients, the agent contract and the new overload tests. The focused run passed
  75 of its original 76 cases; its remaining assertion used the wrong MCP retry
  field name. Correcting it to `retry_after_seconds` passed the targeted rerun.
  The final 18-case rerun includes the added exact-text context case and generated
  contract parity. An earlier run also needed the matching 4.1.2 web bundle;
  the strict app/server bundle version check was retained.
- Real PostgreSQL and a deliberately occupied inference admission gate verify
  both default rejection and explicit recovery. Search and context preserve
  selected spaces, recheck revoked grants and keys, stop further model calls,
  count telemetry once, and resume semantic work when capacity returns.
- Multiple embedding generations never leave partial semantic ranking in a
  keyword fallback. Late token-count contention rebuilds the context from fresh
  evidence and does not mix byte and token counts. Other service errors remain
  errors. No database migration is required.
- Nine TypeScript client tests; matching web and Electron frontend builds;
  repository lint, formatting and release-version checks.
- A real browser against an isolated PostgreSQL workspace verifies the unchanged
  default request, retry hint, hybrid/semantic fallback, visible warnings and
  context byte labels, including exact-text context when its tokenizer is busy.
  Desktop (1440 px) and mobile (390 px) views have no page
  overflow or uncaught JavaScript errors. A simulated 4.1.1 identity disables
  the new control, explains the required server update, and successfully searches
  without sending the unsupported field. The packaged documentation exposes the
  option, warning and 4.1.2 release notes at both widths. The
  [numeric browser record](2026-10-12-busy-fallback-ui.json) preserves the observed
  137-byte context within its 2048-byte fallback budget.

These are correctness and compatibility checks using deterministic model
responses, not throughput measurements or model-quality evaluations. They use no
production memories, cloud model calls or downloaded model weights. Existing
real-model and all six native installation/update gates also passed in the
release pipeline. Peak API/worker memory duplication remains open under issue 13.

See the [release notes](../releases/4.1.2.md) and
[embedding and resource guide](../service/embeddings.md).
