# Telemetry: pinned SQLite allocator decision

**26 October 2026. Do not adopt this prototype.** A private Linux x64 component
using SQLite's bounded allocator passed its functional scope, but the measured
CPU and peak-memory tradeoff does not justify replacing the product backend.
The experiment ended at its fixed stop rule. Product source still uses
`node:sqlite`; V08 stays Building, with collection unavailable and destination
and route null. The 2 MiB / 0.5% resource contract is unchanged.

## Scope and ownership

This follows the [first private adapter](2026-10-26-telemetry-storage-adapter.md)
and the [compiled application results](2026-10-26-telemetry-storage-followup.md).
The component uses source `79dc0f42f486af6c7d3368c48d970f0c39f9abd5` and Node
22.22.0. All prototype code and artifacts remain outside the product repository.
There is no new application daemon, worker or model invocation.

The [official SQLite download](https://www.sqlite.org/download.html) supplied
version **3.54.1**, archive `sqlite-amalgamation-3540100.zip`, 2,990,966 bytes,
with the verified published SHA3-256:

```text
92281c86e2957f9b9305890f9ac04204caa7b677cc868dc326d942689df28e30
```

The separately named runtime enables SQLite's `MEMSYS5` allocator and disables
loadable extensions. Internal function binding isolates it from other SQLite
runtimes. It uses an exclusively owned **512 KiB mapped arena**. After actual
connection closure, the wrapper shuts down its own runtime, unloads it, clears
the arena and unmaps it. Uncertain cleanup retains ownership. It refuses an
already-loaded private runtime and worker-thread imports. This is a main-thread
prototype, not a reviewed cross-platform native API or supply-chain release.

The pinned library is 1,182,728 bytes with SHA-256:

```text
63b4bb277572770ba1e89f3bdb01faf56bb5056880abce55847c05fb99705d14
```

## Functional results and preserved failures

The first binding selection passed eight cases and failed one **test fixture**:
`events.once(worker, 'exit')` rejected on the worker's intentionally emitted
error. The original log and fixture remain retained. Correcting only exit
observation and rerunning that failed case passed; the binding did not change.
The nine combined cases include allocation exhaustion, subsequent independent
work, separate `node:sqlite` use, a second addon instance and worker refusal.
Exhaustion reached 516,160 bytes within the 524,288-byte pool; closure released
the arena and a subsequent connection worked.

The current product store, delivery and transport tests were staged with only
the SQLite import and literal resource/test paths relocated. Original and staged
hashes and reversible rewrites are retained. This selection passed **51 cases
with two Windows-only skips**. It includes real TLS and final-send cancellation;
one original five-second deadline closed its socket 55.018 ms after the deadline.
Combined functional scope is therefore **60 passes and two platform skips**,
not a clean first run, installed acceptance or full resource qualification.

## Fixed resource sequence

The plan permitted exactly four component launches in the order builtin,
private, private, builtin, with no further renderer runs. Each successful launch
performed 64 workflow pairs and one four-byte fake handoff, with **zero network
requests**. Common imports and activity construction preceded the baseline.
There was no forced garbage collection, warmup or idle padding.

The first builtin launch failed before measurement because the probe omitted
the catalog constructor argument. Its log and original fixture remain retained;
that slot was **not replayed**. The corrected fixture completed the original
remaining three slots, so the result is **not a complete counterbalanced design**.
Temporary component roots were removed.

| Remaining slot | CPU, ms | CPU per pair, ms | Pair p95, ms | Ending RSS delta, bytes | Sampled peak RSS delta, bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2: private | 291.891 | 4.561 | 28.213 | 4,579,328 | 5,705,728 |
| 3: private | 262.586 | 4.103 | 22.989 | 4,333,568 | 5,517,312 |
| 4: builtin | 167.323 | 2.614 | 22.856 | 4,866,048 | 4,866,048 |

Against the sole completed builtin observation, private ending RSS was 286,720
and 532,480 bytes lower, but sampled peaks were **839,680 and 651,264 bytes
higher**, and CPU was **74.448% and 56.934% higher**. These are descriptive
comparisons, not stable causal estimates. This synthetic storage burst excludes
actual TLS, renderer work and representative memory activity; it cannot qualify
the product's average CPU gate. Lower ending RSS alone does not establish an
optimization. No resource pass or budget revision was selected.

## Decision and evidence

Keep the existing backend. Do not port or publish this prototype on the strength
of functional compatibility or library unmapping. Further performance work needs
a new implementation hypothesis supported by existing evidence; this experiment
does not authorize another unchanged benchmark. Coverage, sensor/pressure,
whole-wire, tail-latency, utility, ingress-retention and installed-platform
acceptance remain open in the [V08 contract](../implementation/anonymous-product-telemetry.md).

Private receipts are under
`/home/jorqu/mnemion-completion/2026-10-26-telemetry-private-sqlite/`.
`decision.json` hashes 32 original plan, build, staging, test, measurement and
failure records. `component-summary.json` contains all completed observations;
`component-bootstrap-review.json` preserves the lost first slot. The staging
manifest SHA-256 is
`dd989e22a6468b77cfe5df2f6ad23fe37f8c24f8f5e70d0c5a1ec26617f0b101`.
No production setting, resource ceiling, installed application or shared host
was changed by this experiment.
