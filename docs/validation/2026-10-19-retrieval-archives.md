# Archive and question retrieval checks, 19 October 2026

Source batch: **4.24.0**. Reports: [17](https://github.com/Perseusxrltd/mnemion/issues/17)
and [31](https://github.com/Perseusxrltd/mnemion/issues/31). The latest field report
was read again, including its incomplete-index condition. The private reporter's
current encrypted documents were not decrypted or replayed. The committed
fixture contains invented names and identifiers representing the reported
archive, bilingual and mixed-row patterns.

## Actual local-model comparison

The [50-document fixture](../../deploy/retrieval-cases.json) has 13 explicitly
labeled questions, old and current decisions, an eight-clause Markdown table,
English/French questions, rare identifiers, archive-only history and unrelated
notes. The same fixture was run before and after the changes using the pinned
**intfloat/multilingual-e5-small**, 384 dimensions, two inference threads and
an offline model cache. No paid model call, generated vector or fixture embedder
was used. PostgreSQL used distinct non-owner application and worker logins.

Each question ran once with relevance and recent ordering before indexing, then
again after every indexing job completed. The probe calls the actual retrieval
service; it does not claim HTTP, MCP, native-client or original-customer acceptance.
The corpus hash, model generation, implementation fingerprints, per-case ranks,
top-four results and warnings are in the [measurement JSON](retrieval-2026-10-19.json).

| Index / ordering | First before | First after | Top four before | Top four after |
| --- | ---: | ---: | ---: | ---: |
| Pending / relevance | 11/13 | 11/13 | 13/13 | 13/13 |
| Pending / recent | 8/13 | 12/13 | 13/13 | 13/13 |
| Complete / relevance | 12/13 | 13/13 | 12/13 | 13/13 |
| Complete / recent | 6/13 | 12/13 | 13/13 | 13/13 |

The remaining recent-order target is second: a related current school decision
precedes the explicitly labeled home-education note. Pending indexing still
weakens cross-language relevance. The public index warning remains visible;
the fix does not pretend to supply missing vectors. This is a small development
regression set, not a held-out accuracy benchmark or evidence for every language.
The fixture was fixed before the baseline; the archive-only miss found in that
baseline led to an additional correction.

Observed median query times ranged from 255–383 ms before and 303–475 ms after.
The final run shared this WSL CPU with other checks, so these observations do
not establish a latency regression or improvement. There is no additional
inference, database query or candidate expansion in the ranking change.

Repeat from the locked development environment, after preparing the ordinary
pinned model cache:

```sh
python -m deploy.retrieval_regression \
  --cache /path/to/prepared-model-cache \
  --output build-tmp/retrieval-observation.json
```

The probe starts and cleans up its own disposable PostgreSQL instance through
the development `pgserver` package. It never reads a user profile, connects to a
workspace, sends mail or publishes notes. Exact tie ordering can vary with fresh
database identifiers; retain the raw observations when comparing runs.

## Focused service checks

**90 passed** across current ranking, question retrieval, passage chronology,
general recall, identifiers and matching passages. Added cases verify both
indexing states, preserved historical dates, archive-only queries, strong old
evidence ahead of weak fresh notes, explicit archive/strict-date controls,
bilingual keyword support and unchanged relevance/similarity filters. Existing
scope, source access, deletion, chronology, evidence and SDK checks are retained.

The TypeScript client's **17 tests passed**. The production Studio type-check
and build passed with the new warning and result explanations. **18 evaluation
checks passed**, including queued-before-upgrade runs, refusal to mix service
versions, cancellation, revocation and erasure. The test queue is explicitly
cancelled after its isolated startup check, preserving the global runner lease.
The final migration preflight passed **25 checks**. The packaged web Studio
contains 445 verified files and 125 frontend license components.

## Intel Mac dependency correction

Main-source CI run [39303012547](https://github.com/Perseusxrltd/mnemion/actions/runs/39303012547)
failed three Intel Mac managed-install cases while preserving the existing
runtime. A binary-only resolution of the frozen 4.23 lock independently
reproduced the missing `argon2-cffi-bindings==26.1.0` wheel. Version 25.1.0
supplies the Intel wheel. The upstream [changelog](https://github.com/hynek/argon2-cffi-bindings/blob/26.1.0/CHANGELOG.md)
identifies the same vendored Argon2 source, `f57e61e19229e23c4445b85494dbf7c07de721cb`,
in both releases. Other platforms retain 26.1.0.

The new binary preflight rejected that frozen lock and accepted the corrected
lock on all five service targets. It checks Python 3.12 here, macOS 13 Intel,
macOS 14 ARM, Linux glibc 2.28 x64/ARM and Windows x64. Windows ARM desktop uses
the existing x64 service engine. This proves resolution only; native execution,
installed updates and publication remain separate release gates. The failed
4.23 source is preserved, and its release build was cancelled; 4.24 carries the
fix and the KeePass work.

## Remaining scope

Current-state truth still requires source evidence. Filename version numbers,
archive names and timestamps do not prove supersession. Ambiguous/undated
history, historical Git blame, broader held-out multilingual/provider tests and
fleet throughput remain on the roadmap. The original office database/vault has
not been recovered by these checks. Strict full-product coverage remains
**17/64 (26.6%)**; closing these bounded reports does not change that count.
