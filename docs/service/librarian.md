# The configurable memory librarian

For a workspace hosted by Studio, source 4.33 adds [model-provider setup in the app](desktop-models.md).
Saved profiles and keys remain separate from each space's processing approval.

The shared librarian lets a space use an operator-approved local or cloud model
to propose organization and maintenance. Open **Librarian** in Studio, select
an approved model as a space administrator, and enable processing. Reviewers can
then generate, inspect, accept, reject and undo proposals. No model is enabled by
default, and scheduled processing is a separate opt-in setting.

The same service works with Windows, macOS and Linux clients. Models run at the
configured endpoint; a desktop client does not need model weights, a GPU or an
Ollama installation. A small computer can connect to its organization's server.

For a space with an approved Git journal, 4.16.0 also offers
[automatic filing and archival](git-journal.md#automatic-filing-and-archival)
under **Git journal**. It creates readable Markdown views from current records
and moves older journals intact to `_archive`, without requiring a model call.
Its schedule is separately enabled and uses the journal's publisher permissions.
Model-assisted proposals and review below keep their existing controls.

## What a run does

| Task | Input | Result |
| --- | --- | --- |
| Organization | One memory per independent model call | Proposed title, additional tags and summary |
| Review | A bounded batch from one space | Possible links, duplicates, contradictions or stale claims |

Organization proposals preserve the memory's original text, source revision,
source offsets, attachments, claim status and unrelated metadata. Acceptance
creates a normal versioned revision and indexing operation. Tags are added to an
existing string list; an incompatible tag format requires direct editing.
The summary is stored in the memory's `summary` metadata field. Inspect the diff
before applying it. Undo restores the previous title and metadata only while the
applied revision is still current; later human changes cannot be overwritten.

Acknowledging a review finding records a human decision. It does not merge,
delete, link records in the canonical graph, or mark a claim verified. Findings
cover only the supplied batch, not every possible pair in the vault. There is no
claim of a complete contradiction or duplication scan.

Every suggestion must quote exact supplied memory text and identify the target
and related memories. The service rejects unknown IDs, fabricated quotations,
unsupported actions, generated tool calls and malformed JSON. Model confidence
is an uncalibrated model opinion, not measured accuracy. Human review remains
necessary: a quotation can be real while a conclusion drawn from it is wrong.

Expand **Source evidence** on a proposal to see every supplied memory ID, its
version and immutable revision ID, alongside exact quotations. Inputs the model
did not quote are also listed. **Selected memories & outcomes** in run history
shows each input's revision and whether it was checked, skipped or not processed.
The before/after diff uses the source snapshot from proposal generation.

## Configure a local model

Install and run a suitable model server separately. Mnemion never starts a model
daemon, pulls language-model weights or creates a provider account. Configure
`MNEMION_LIBRARIAN_CONFIG` on each API host to point to a private JSON file:

```json
{
  "profiles": [
    {
      "id": "local-librarian",
      "label": "Local memory librarian",
      "protocol": "ollama",
      "endpoint": "http://127.0.0.1:11434/api/chat",
      "model": "YOUR_INSTALLED_MODEL_NAME",
      "revision": "YOUR_DEPLOYED_MODEL_DIGEST",
      "tokenizer": {"kind": "utf8"},
      "context_budget": 8192,
      "max_output_tokens": 1024,
      "timeout_seconds": 45,
      "server_threads": 2,
      "keep_alive_seconds": 0,
      "thinking": false
    }
  ]
}
```

Replace the two identity placeholders with the actual installed model and its
revision. Choose a model that can follow the JSON output contract. Ollama's
`thinking` option can be `null` to leave that choice to the model server. Context,
output and CPU settings bound the request, but do not make a large model fit in
small RAM. Enforce memory limits on the model server itself and measure its real
resident memory before enabling a schedule.

The API runs jobs through its restricted database login, using the initiating
reviewer's current identity. The separate indexing worker does not need this
configuration or provider credentials. Apply the new schema migration and restart
API processes when deploying the feature or changing model configuration.

Inspect configured choices without generating text:

```bash
mnemion-service librarian-models
mnemion-service librarian-models --prepare local-librarian
```

Preparation only prepares a pinned tokenizer, if one is configured. UTF-8
accounting needs no download. Tokenizer choices use the same pinned Hugging Face
revision/checksum or private file/checksum format as [embedding models](embeddings.md).
Use `MNEMION_MODEL_OFFLINE=1` to require tokenizer files already in the cache.
This flag does not disable an explicitly approved HTTP endpoint.

## Cloud and company gateways

Use `protocol: "openai"` and the complete Chat Completions endpoint, such as a
company gateway's `https://models.example.com/v1/chat/completions`. Set `model`
and `revision` to the deployment identities, and `api_key_env` to the name of a
private server environment variable holding the existing provider key. Never
put the key in the profile file, source control, Studio or a URL.

OpenAI-compatible servers may choose `output_token_parameter: "max_tokens"`
instead of the default `max_completion_tokens`. Set `json_mode: false` only for
servers that do not accept `response_format`; their output must still satisfy the
same JSON contract. `temperature` defaults to omitted. An explicit `response_model`
handles a deployment name that differs from the model name returned by the API.
Azure-style gateways can use `api_key_header: "api-key"` and one `api-version`
query parameter. Other native provider APIs require a compatible gateway.

Non-loopback endpoints require HTTPS. Redirects, URL credentials and implicit
environment proxies are disabled. `ca_bundle_env` can name a private trusted CA
bundle path; TLS verification cannot be switched off. A space administrator must
explicitly approve sending its selected text to a non-loopback endpoint. The
profile fingerprint changes when its processing configuration changes, requiring
the space's configuration to be reviewed and saved again. The operator must also
pin remote deployments: a response name cannot attest the remote model's weights.

In Compose, mount the private profile and any tokenizer file read-only into the
API container using a private Compose override, and supply the corresponding
environment variables there. Keep provider keys out of the base Compose file and
shared repository. `127.0.0.1` inside a container is that container, not the host;
use a reachable HTTPS model gateway or run the standalone API alongside the local
model server. API cache mounts are read-only, so prepare pinned tokenizers first.

## Budgets, schedules and monitoring

- One live librarian job per database deployment, across API instances. At most
  12 memories per run, up to 12 suggestions per review batch and a 10-minute run
  deadline. The default space limit is four memories per run.
- A request defaults to 45 seconds, 1,024 output tokens and a 256 KiB response
  ceiling. Operators can set stricter limits; the maximum timeout is 90 seconds
  and the maximum response size is 1 MiB. The timeout covers the complete HTTP
  exchange, including connection, headers and body. A cancelled or expired
  request closes its client transport; partial packets cannot renew the deadline.
  No hidden provider retries occur. A remote model may continue computation after
  its client disconnects, according to that provider's behavior.
- Context admission reserves room for output and chat overhead. By default it
  conservatively accounts input text as UTF-8 bytes, not measured model tokens.
  A pinned tokenizer enables model-token accounting. The model server must still
  enforce its own context limit. Oversized input is skipped without being sent;
  the service does not silently truncate the evidence.
- A durable per-space call budget defaults to 24 calls per UTC day. Reservation
  happens before sending text and remains consumed after failure or interruption.
  This limits call count, not currency charges. The chosen provider may charge.
- Each attempted revision is recorded before the call. Ordinary and scheduled
  sweeps skip unchanged revisions already attempted with that profile and task.
  To retry deliberately, enter specific memory IDs in Studio or the SDK. New
  source revisions or a newly approved model configuration can be examined again.
- Optional hourly, daily or weekly sweeps use the configuring administrator's
  identity and key. Expired/revoked keys cannot acquire substitute credentials.
  Pause processing to cancel queued work and prevent additional requests.
  A cancelled request retains the shared worker slot until its caller returns or
  the lease expires; another API process cannot immediately overlap that call.
- Proposals have a bounded review backlog; review it before generating more.
  History pages are bounded. Studio shows selected/checked/skipped memories,
  proposals, reserved/completed calls, input units, reported output tokens,
  transferred bytes, latency, failures and the reproducible configuration.

Usage for an interrupted request can be unknown. Reserved call counts remain
durable; completed-request counters and provider-reported usage must not be
presented as a complete provider invoice. Output tokens are absent when the
provider does not report them. No memory text enters these general counters.

## Permissions, deletion and recovery

All operations require current access to the space; configuration requires its
administrator role and jobs/decisions require reviewer access. Provider-managed
source leases are checked through the same space policy as ordinary retrieval.
Access, configuration, source revisions and job leases are rechecked before the
call and before accepting results. Cancellation or revocation discards late
results. Already-sent text cannot be recalled from an external provider.

Every generated finding depends on every memory supplied to its model request,
including inputs it did not explicitly cite. Deletion or quarantine clears the
affected generated text and proposal references. Run history retains identifiers,
versions and numeric outcomes, without source text. Restoring a backup reconciles current
deletions, disables model schedules, clears outbound approval, cancels old jobs
and rotates keys. An administrator must explicitly re-enable processing.
Independent provider logs, backups and exported copies have their own retention.

The versioned API is under `/v1/spaces/{space_id}/librarian`; the Python and
TypeScript SDKs expose settings, model choices, runs, their bounded input lists,
proposals and decisions. `GET /runs/{run_id}/items` returns at most 12 input
records and requires current reviewer access to the run's space.
See the generated [OpenAPI contract](openapi.json). Configuration and safeguards
are validated with real PostgreSQL and synthetic HTTP transports; these tests do
not certify the reasoning quality of any live model or provider account. Model
comparisons, organization-wide semantic grouping and calibrated librarian quality
evaluations remain on the [roadmap](../ROADMAP.md).

Protocol references reviewed on 2026-10-10:
[Ollama chat](https://docs.ollama.com/api/chat) and
[Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create).
