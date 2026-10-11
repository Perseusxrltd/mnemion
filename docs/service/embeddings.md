# Embedding models, reindexing and resources

Mnemion keeps an independent embedding generation for each space. Space
administrators can build a candidate while the active index serves users,
preview its search, compare evaluations, and activate it only after every
retained, non-deleted source revision has coverage. Obsidian paths, memory IDs,
source evidence and permissions do not change with the embedding model.

The default remains the pinned multilingual E5 Small model. It is a measured
baseline, not a claim that one model is best for every language or company.
Choose with your own versioned evaluation set, resource limits and privacy needs.

## Available execution options

| Choice | Runs where | Intended use |
| --- | --- | --- |
| `e5-small` | Memory server CPU, quantized ONNX | Existing multilingual baseline; 384 dimensions |
| `bge-small-en` | Memory server CPU, quantized ONNX | Small English alternative; 384 dimensions; 34,014,426-byte model download, excluding tokenizer/configuration files |
| Ollama `/api/embed` | An operator's already-running model server | Models such as Qwen3 Embedding 0.6B; explicit model identity and dimensions |
| OpenAI-compatible `/v1/embeddings` | Approved local server, company gateway or cloud | User-selected models and optional reduced dimensions; cloud providers may charge |

The desktop client needs no embedding weights or GPU. The model runs on the
memory server or configured endpoint. Download size does not equal resident RAM.
The registry serializes inference within each API/worker process, defaults to two
CPU threads for local models, and loads local weights only when used. Two enabled
local models may both remain cached in that process; API and worker processes have
separate memory. Set container/service CPU and memory caps for the actual host.

From 4.0.3, each local model shares one tokenizer vocabulary between source
counting/chunking and inference. A lock restores the model's original padding
and truncation settings before inference; source spans still cover the complete
Unicode document. Pinned E5/BGE tests verify identical source-tokenizer semantics.
This changes memory allocation, not the embedding generation, and requires no
reindex. The [resource comparison](../validation/2026-10-11.md) measured E5 loading
at 788.4 → 492.4 MiB and a 35-chunk document at 1342.9 → 1059.1 MiB of process RSS.
Those are one controlled CPU run per implementation, not universal RAM limits or
retrieval-quality claims. API and worker remain separate processes; their models
are not shared across process boundaries.

Mnemion does not start an Ollama daemon, pull remote-server models, provision a
cloud account, or make a paid call during configuration or model preparation.
The operator installs the desired model separately. Model cards and API formats
reviewed on 2026-10-10:

- [Multilingual E5 Small](https://huggingface.co/intfloat/multilingual-e5-small)
- [BGE Small English v1.5](https://huggingface.co/BAAI/bge-small-en-v1.5)
- [Qwen3 Embedding 0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B)
- [Ollama embeddings API](https://docs.ollama.com/api/embed)
- [OpenAI embeddings guide](https://developers.openai.com/api/docs/guides/embeddings)

Vendor/model-card benchmarks are not Mnemion evaluations. Real CPU integration
tests cover E5 and BGE; HTTP protocol tests use synthetic local transports and
do not certify a particular live cloud account or Qwen deployment.

## Operator configuration

### Native runtime compatibility

From 4.0.7, Intel Mac servers select **ONNX Runtime 1.23.2** with Python
**3.12 or 3.13**, the newest upstream runtime shipping Intel Mac wheels. Newer
ONNX releases publish Apple-silicon wheels only; Python 3.14 has no compatible
Intel Mac wheel. Other platforms retain the newer runtime in the lockfile.
Use `uv sync --locked --python 3.13` for a source installation, and do not force
a wheel for a different processor architecture. The pinned model weights,
tokenizer identity and generation remain unchanged, so this packaging fix does
not require reindexing.

The desktop client includes its own small runtime and does not load ONNX or
require the user to install Python. An Intel Mac can also connect to a service
hosted on other hardware or use the Linux container deployment. Native Mac CI
runs both pinned E5/BGE model checks on the selected runtime; broader throughput
and hardware comparisons remain separate evaluations. See the
[upstream distributions](https://pypi.org/project/onnxruntime/1.23.2/#files).

### Approved profiles

Set `MNEMION_EMBEDDING_CONFIG` to a private JSON file on every API and worker host.
Without it, only E5 is enabled. To make both small CPU models available:

```json
{
  "local_profiles": ["e5-small", "bge-small-en"],
  "remote_profiles": []
}
```

With the database owner login configured, apply migrations and register approved
generation identities. The running API and worker retain non-owner credentials:

```bash
mnemion-service migrate
mnemion-service models --register
mnemion-service models
mnemion-service prepare-model --profile bge-small-en
```

Restart API and worker processes after changing their configuration. Use the same
configuration, package lock and tokenizer runtime versions on each host. Listing
and registering models do not run inference. `prepare-model` verifies/downloads
pinned local assets; for an HTTP profile it prepares only the tokenizer.
`MNEMION_MODEL_OFFLINE=1` requires any tokenizer/ONNX files to exist in
`MNEMION_MODEL_CACHE`; it does **not** disable an explicitly configured HTTP provider.

For an existing Ollama server, add a profile such as:

```json
{
  "id": "company-qwen",
  "label": "Company Qwen3 Embedding 0.6B",
  "protocol": "ollama",
  "endpoint": "http://127.0.0.1:11434/api/embed",
  "model": "qwen3-embedding:0.6b",
  "revision": "REPLACE_WITH_THE_DEPLOYED_MODEL_DIGEST",
  "dimensions": 1024,
  "tokenizer": {"kind": "utf8"},
  "query_prefix": "Instruct: Given a web search query, retrieve relevant passages that answer the query\nQuery: ",
  "chunk_tokens": 512,
  "overlap_tokens": 64,
  "max_query_tokens": 2048,
  "max_input_tokens": 4096,
  "batch_size": 8,
  "keep_alive_seconds": 30,
  "server_threads": 2
}
```

Place that object in `remote_profiles` and replace the revision with the actual
deployed identity. Verify the server's model card and input-template behavior.
An endpoint's model alias can change without its response name changing:
Mnemion checks the returned model name and dimensions, but cannot independently
attest remote weights. The operator must freeze the deployment/revision and
register/reindex changes. Local ONNX model and tokenizer bytes are SHA-256 checked.

An optional OpenAI-compatible cloud profile can use:

```json
{
  "id": "approved-cloud",
  "label": "Approved cloud embeddings",
  "protocol": "openai",
  "endpoint": "https://api.openai.com/v1/embeddings",
  "model": "text-embedding-3-small",
  "revision": "REPLACE_WITH_YOUR_DEPLOYMENT_REVISION",
  "dimensions": 1536,
  "api_key_env": "MNEMION_EMBEDDING_PROVIDER_KEY",
  "tokenizer": {"kind": "utf8"}
}
```

No credentials belong in the JSON file or repository. `api_key_env` references
an existing server environment variable. `send_dimensions: true` sends the
configured dimensions when supported. Azure-style gateways may use
`api_key_header: "api-key"`, an `api-version` query parameter and an explicit
`response_model` if the returned model differs from the deployment name.
No other endpoint query parameters are accepted. Non-loopback endpoints require
HTTPS; redirects, URL credentials and implicit environment proxies are disabled.
For company certificate authorities, `ca_bundle_env` names an environment variable
holding the trusted CA bundle's path. TLS verification cannot be disabled.

## Chunk and context budgets

For `tokenizer.kind: "utf8"`, fields named `chunk_tokens`, `overlap_tokens`,
`max_query_tokens` and `max_input_tokens` are explicitly **UTF-8 byte budgets**.
They are not measurements of the remote model's tokenizer. Returned context packs
include `token_count_unit: "utf8_bytes"`; Studio labels these values as bytes and
telemetry does not add them to model-token counters. The model server still
enforces its own token/context limit and must reject oversized inputs.

For actual model-token budgets, select a pinned tokenizer:

```json
{
  "kind": "huggingface",
  "repository": "Qwen/Qwen3-Embedding-0.6B",
  "revision": "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3",
  "sha256": "def76fb086971c7867b829c23a26261e38d9d74e02139253b38aeb9df8b4b50a"
}
```

This fetches only `tokenizer.json`, not Qwen weights. Alternatively use
`{"kind":"file","file_env":"MNEMION_TOKENIZER_FILE","sha256":"<64 lowercase hex characters>"}`
for a private local tokenizer file. The format must be a Hugging Face Tokenizers
JSON file. Operator-supplied tokenizer/model compatibility remains the operator's
responsibility. File hashes and the tokenizer runtime form part of the generation.
Changing prefixes, tokenizer, dimensions, endpoint or declared revision creates
a distinct generation; it never overwrites an existing vector space.

Source offsets always use Unicode characters. Prefixes count toward input limits.
Every chunk is validated before the first document request. Ollama receives
`truncate: false`; responses with the wrong model, duplicate/missing output
indices, wrong dimensions, non-finite values or zero vectors are rejected.

Defaults bound each document to 256 KiB, 512 chunks, eight inputs per request,
4 MiB per response, 30 seconds per request and 120 seconds per document. These
limits are configurable within validated upper bounds. The provider adapter does
not retry internally; durable jobs handle bounded retry/backoff. Five failed job
attempts require a reviewer/admin retry. Partial document batches are never
published as a completed index revision.

## Inference admission

Each API or worker process shares one admission gate across its approved embedding
profiles. It executes **one inference at a time**, with at most **16 waiting
callers** and a **2-second admission wait** by default. This absorbs short bursts
without allocating concurrent model activations. These are queue settings, not
a promise of a particular requests-per-second rate or loaded-model RAM limit.

Configure `MNEMION_MODEL_MAX_QUEUED` (0–64) and `MNEMION_MODEL_WAIT_SECONDS` (0–5)
on API and worker hosts, then restart them. A full queue or expired wait returns
`503 inference_busy` and HTTP `Retry-After: 1`; no inference is started for that
rejected request. Python and TypeScript SDKs respect server retry hints, capped
at 30 seconds per delay, only for safe reads or writes with an idempotency key.
MCP errors carry the retry hint in `structuredContent`. Queue counters in runtime
insights report active, waiting, completed, failed and rejected calls plus time
spent waiting/executing, without memory text or caller labels.

Keep `MNEMION_MODEL_THREADS` at the measured host capacity (default 2). Increasing
queue length does not make the model execute faster. API and worker processes
still maintain separate caches; low-memory shared-model operation and idle-model
unloading remain tracked improvements. Validate with the real corpus, concurrent
agents, source indexing and librarian workload before increasing resource caps.

## Choosing and activating a model

1. In the selected space, open **Embedding models** as a space administrator.
2. Choose a registered profile. Explicitly approve the displayed destination for
   any non-loopback endpoint. That choice covers retained revisions, new memory
   text and search queries for this space.
3. Build the candidate. The worker scans at most 100 revisions per scheduling
   pass and pauses scanning at 1,000 unfinished candidate jobs. New writes add
   work for both active and candidate generations. Failed work remains visible.
4. Preview candidate search and open **Evaluate this candidate**. The evaluation
   lab can freeze either the active or candidate generation with the same test
   set. Choose development questions before using held-out results.
5. Activate when ready. A transaction excludes concurrent writes during the final
   coverage check and pointer change. A query racing a switch gets a retryable
   conflict rather than mixing different vector dimensions.

Pause stops new candidate indexing; an in-flight document may finish. Cancel
invalidates pending/leased candidate work, and a cancelled worker cannot publish.
Neither action deletes source memories. Previously built vectors remain for
controlled rollback; selecting a prior profile reuses them and indexes missing
revisions before another guarded activation. This uses extra disk space while
retaining rollback options. Delete/purge applies to all generations.

Multi-space searches compute distances separately for each generation, then fuse
ranks. Their `index.generation_id` is null when several generations participate;
`generation_ids` and `space_generations` identify them explicitly. Context across
different models uses an explicit UTF-8 byte budget. Applications must still
budget their final prompts with their answering model's own tokenizer.

## Recovery and permissions

Expired/suspended connector access defers indexing before inference without
consuming the retry budget. Withdrawn sources and deleted memories cannot publish
new vectors. Keys/grants and model choices are rechecked around query inference.
Space writers can contribute while reindexing; they cannot change profiles or
approve egress. Candidate preview/evaluations require reviewer access.

A database restore pauses HTTP active-model processing and candidate indexing;
old endpoint consent is not reused automatically. **Embedding models** shows
the reapproval controls. Restore the correct private operator configuration,
review the destination, then resume explicitly. You may instead cancel an old
candidate and build/activate a local model while the old HTTP model stays paused.
Provider credentials and tokenizer files outside the database need their own
protected backup procedure. See [recovery](recovery.md) and [privacy](privacy.md).

API routes are listed in the bundled OpenAPI contract under **Embedding models**.
Both SDKs support settings, candidate start/control and processing resumption.
Model configuration is intentionally an operator concern; memories and API
callers cannot supply arbitrary embedding endpoints.
