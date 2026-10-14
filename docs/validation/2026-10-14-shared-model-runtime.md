# Shared managed model runtime — 2026-10-14

The 4.2.5 source removes duplicate local embedding ownership from supervised
API/worker deployments. One worker registry serves document indexing and API
query/context/evaluation calls. Native local workspaces already share one
registry. Independently deployed services retain their existing ownership.
This addresses the duplicate and retained model allocations reported in
[issue 13](https://github.com/Perseusxrltd/mnemion/issues/13), together with the
previous tokenizer, idle-session and glibc heap cleanup improvements.

## Offline model comparison

Run the reusable probe with a previously prepared pinned model cache:

```sh
python -m benchmarks.shared_model_resources --cache /private/model-cache --profile e5-small
```

The probe uses fresh spawned processes, one CPU thread per model, synthetic
multilingual text and no model downloads or cloud calls. It compares two local
model owners with a worker-owned model accessed over the actual pinned TLS
connection. It stops only its own probe children after recording both live
processes. The measurement below used Linux x64, Python 3.12 and a 3 GiB process
group limit with no swap; this limit is not a product minimum.

| Measurement | Separate owners | Shared worker | Reduction |
| --- | ---: | ---: | ---: |
| Combined resident memory (RSS) | 1,196.3 MiB | 749.3 MiB | 37.4% |
| Combined proportional resident memory (PSS) | 1,142.4 MiB | 726.9 MiB | 36.4% |
| Combined unique resident memory (USS) | 1,102.4 MiB | 718.3 MiB | 34.8% |
| API model-process RSS | 502.4 MiB | 42.6 MiB | 91.5% |

RSS can count shared pages more than once; PSS and USS are included to distinguish
that accounting effect. The worker indexed 11 chunks and the API performed one
query. Query vectors, document vectors and exact Unicode source spans produced
identical hashes. The API kept no local ONNX session or tokenizer. Generation
fingerprints and on-disk model bytes were unchanged.

The [numeric record](2026-10-14-shared-model-measurements.json) includes the
synthetic source hash, runtime versions, source-file hashes and per-process
measurements. After the run, the probe's unused BGE option spelling was corrected
to `bge-small-en`; the measured E5 execution path is unchanged. This is a model-process comparison, not whole-host memory,
retrieval quality, steady-state latency or production throughput. Cold model
loading differs between the two cases; their timings must not be presented as
a warm-query speed comparison. Other hardware, models and workloads can differ.

## Behavior and boundaries

Eight focused checks passed against the final implementation, including:

- Real pinned loopback TLS, private credentials, unchanged Unicode spans for
  both small and large documents, shared ownership and bounded queue errors.
- Rejection of a different TLS listener before memory text is sent, and client
  recovery after the worker rotates its certificate and credential.
- Current CLI activation under an older Supervisor's existing role contract,
  with a documented opt-out and no fallback to another loaded API model.
- Real PostgreSQL and Supervisor children: API and worker startup, worker crash,
  certificate rotation, API crash, fresh authenticated worker observations and
  clean shutdown. Observing the worker did not load a model.
- Existing reviewer/administrator and revoked-access boundaries for insights.

The earlier local-model cleanup regression set also passed. The typed client
and production Studio build passed with the worker resource panel. Release
association checks require passing public evidence, reject a changed or draft
release, and leave reopened labeled reports open.

There is no new database migration or model generation. The API's own counters
retain their existing scope; worker gauges are separate and administrator-only.
Busy/unavailable observations do not invent zero values or reset idle timers.
Local sharing is enabled only for supervised processes; it creates no public
endpoint and provisions no service. Provider model consent is unchanged.

Public package, automatic-update and actual shared-host adoption results are
recorded separately in [release status](../RELEASE_STATUS.md). This source
validation does not claim that the customer's running host has already upgraded.
