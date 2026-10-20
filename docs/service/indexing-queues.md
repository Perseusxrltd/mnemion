# Indexing queues and busy workspaces

A successful save first returns a durable operation receipt. Its embedding can
still be **accepted** or **indexing** before becoming **ready**. Poll the receipt
with a bounded interval; repeated polling does not make the worker faster. A
source import, model cold start, slow provider or resource limit can delay
completion without losing the saved record.

## Dispatch in 4.35

After migration 029, each configured indexing worker selects work in this order:

1. An eligible purge, in the existing availability/creation order.
2. The eligible organization that has waited longest for an indexing turn.
3. The eligible space within that organization that has waited longest.
4. That space's oldest available indexing job.

An organization receives one turn even when it has several active source spaces.
Each claimed job advances persistent organization/space dispatch counters.
These use a database sequence and do not depend on a wall clock or an individual
worker's in-memory history. Empty, paused or incompatible queues do not consume
turns. Existing model-level rotation remains in effect.

Claim transactions retain the narrow worker-only function and skip locked work.
They finish before model inference. Concurrent workers do not share a lease;
an abandoned lease remains subject to its existing expiry/retry rules. Current
source access, active/candidate model selection and administrator approval are
still checked before publishing vectors. The API role cannot claim jobs.

Purges continue to work without an available embedding model and take priority
over indexing. The API's immediate withdrawal and visibility rules are unchanged;
physical cleanup still has its own operation receipt. Existing backup and
deletion-ledger policies remain necessary.

## Limits and observation

Dispatch fairness is between jobs. A calculation already in progress retains its
lease; it is not forcibly interrupted. Jobs within the same space keep their
existing order. Hardware, record sizes, model settings and provider limits
determine actual throughput. Sustained deletion work can defer embedding work.

In **Insights & evaluations**, inspect the space's pending/leased counts, oldest
job age and queue latency. **Models & resources → Shared model worker** shows
the worker's actual memory use and inference activity separately from the API.
A running API process alone does not mean embeddings have caught up. Diagnostics
remain scoped to the caller; cross-process resource observations require
administrator access.

For agents, retain each write receipt and inspect its operation state. Use
backoff when work is still pending, keep total request/time budgets, and reserve
capacity for any required cleanup. Read fresh status after an uncertain reply
instead of issuing another write with a different idempotency key. A failed
evaluation or stress cycle must retain its failure and outstanding cleanup.

See [resource budgets](memory-resources.md), [insights](insights.md),
[source permissions and inventories](connectors.md) and
[managed schema upgrades](managed-upgrades.md).
