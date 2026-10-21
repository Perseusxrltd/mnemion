# Cooperative inference during long local indexing

Recorded 20 October 2026 for the prepared **4.43.0 source candidate**. The later
[4.43 publication, actual update and live contention acceptance](2026-10-21-443-acceptance.md)
is recorded separately from this source experiment.
The original 4.41 deployment's semantic HTTP 503 had no retained error body;
this study establishes a reproducible contention mechanism without assigning
that historical failure a definitive cause.

## Reproduction and source correction

The original `LocalEmbedder.document()` held shared execution for a complete
document of up to 512 chunks. Query admission could expire while completed
inference batches offered no turn to the waiting query.

An isolated diagnostic used the real local embedder, inference gate, tokenizer
wrapper and RAM policy with a deterministic fake model. Its 32 batches each took
approximately 91–94 ms. A concurrent query still returned `inference_busy` after
2,035.6 ms, with 22 document batches complete and indexing still active. The
512-chunk document completed in 3,210.0 ms. A later query succeeded. Socket
creation was disabled; no model download, cloud call or production request occurred.

The source retains one admission token for the whole document and yields
execution to existing FIFO waiters after each completed batch. Both the native
iterator and tokenizer context finish before yielding. On resumption, model
preparation and RAM admission are checked again, so another profile's eviction
or a changed budget cannot leave stale native-session references in use.

CPU batches begin at one chunk and adapt toward a **250 ms target**, never above
the RAM policy's batch cap. Only one native call executes at once. The existing
new-request admission wait remains unchanged; cooperative document waits share
one **30-second cumulative allowance** rather than receiving a fresh allowance
at every batch. A timeout retains the running foreground caller's ownership and
leaves the document operation failed/retryable. Operation completion counters
remain per operation, and execution time excludes time yielded to other callers.

## Focused and real-model evidence

**70 focused tests passed** in 7.96 seconds. Coverage includes queued-query turns,
FIFO ordering, cumulative deadlines, slow foreground completion, timeout cleanup,
maintenance exclusion, real local and authenticated loopback-broker paths,
model eviction, changed RAM policy and unchanged 512-span fixture output.

A separate comparison used the cached, pinned **BAAI/bge-small-en-v1.5** model,
one model thread and a 512-chunk synthetic document on Linux x64 under WSL2.
Both models were prepared and warmed before the measured indexing operation.
Network connections were blocked; model downloads, cloud calls, production
requests and production writes were all zero.

| Measurement | Original implementation | Corrected source |
| --- | ---: | ---: |
| Concurrent query during indexing | HTTP 503, `inference_busy`, after 2.000 s | HTTP 200 in 0.269 s |
| Complete 512-chunk indexing | 63.829 s | 61.869 s |
| Peak measured process RSS | 927,989,760 bytes | 422,576,128 bytes |
| Maximum simultaneous native calls | 1 | 1 |

The query was submitted while indexing was active in both runs. All **512 source
spans and 512 × 384 vector components matched exactly** in the saved outputs;
maximum absolute component difference was zero and the generation identifier
was unchanged. These are measurements of one synthetic CPU workload, not a
retrieval-quality evaluation, whole-host memory measurement or fleet benchmark.

The baseline ran at source `3bf2a84621a37808b073e2ee53ca7ede3ec4c056`.
The corrected experiment used the uncommitted source changes prepared for 4.43;
its receipt records the base revision and exact tested-file hashes. Original
and corrected receipts and vector arrays remain separate. No historical failed
result was replaced with the later success.

## Withheld 4.42 native gate and diagnostic addendum

[The 4.42 Windows x64 installed-workspace gate](https://github.com/Perseusxrltd/mnemion/actions/runs/39457153644/job/118751243848)
failed during the `create` phase with `Missing setup field`, before `localCreate`
started model/database setup. The process, window and tray remained present.
The retained artifact did not identify which of four fixed input selectors,
setup step or route was involved. Relevant setup/probe files were byte-identical
to the passing 4.41 source, so the exact cause remains unresolved. **4.42 remains
withheld**; this is not evidence of a diagnosed and fixed setup bug.

The 4.43 batch adds diagnostics to that existing probe and its artifact writer:
the failed selector is restricted to a fixed list, the setup step to 1/2/3 or
null, and the route to `workspace`, `help` or `other`. The artifact sanitizer
copies only those bounded fields. Input values, arbitrary routes, page text
and credentials are excluded from the new diagnostic payload. Existing waits,
deadlines, setup behavior and release acceptance gates are unchanged.

The Electron build and **226 existing tests passed**. Separately, **24 synthetic
cases** exercised the actual renderer helpers and artifact sanitizer, including
sensitive sentinel values and invalid classifications. Locked client and frontend
production builds also passed. These checks validate diagnostic behavior; they
do not replace a successful installed-workspace test or establish the missing
field's cause. The original failure and source comparison remain under
`2026-10-20-442-native-failure/`, alongside `443-electron-tests.log` and
`443-setup-diagnostics-result.json` for the added diagnostics.

## Limits and acceptance still required

A native call is not preempted. Cold model loading, whole-document tokenization,
a single slow chunk or a saturated queue can still exceed query admission.
Sustained competing work can exhaust the cumulative cooperative allowance;
ordinary durable indexing retry and explicit lexical fallback remain available.
The adaptive target is not a maximum-response-time promise.

The private real-model evidence is under `2026-10-20-inference-fairness/`:
`real-model-original.json`, `real-model-corrected.json`, their corresponding
`.npz` outputs and `focused-final.log`. The original deterministic reproduction
is preserved separately in `2026-10-20-semantic-contention-review/reproduction.json`.
Native packaging, public update delivery and the actual shared-host/Windows cycle
subsequently passed. The [later acceptance](2026-10-21-443-acceptance.md) also records
two live semantic queries during the same indexing operation and final document
readiness; its observation is operation overlap, without native-batch instrumentation.
Broader hardware/workload acceptance remains required. The
[65 requirements](../PRODUCT_REQUIREMENTS.md) and their statuses are unchanged;
R04 remains partial.
