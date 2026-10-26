# Company-policy path refusal — 27 October 2026

In the original [4.46.30 native run 40412022100](https://github.com/Perseusxrltd/mnemion/actions/runs/40412022100),
both Windows architectures failed the company-policy cold-start check. Windows
can report `ENOENT` when an ancestor is a regular file; the old implementation
could treat that invalid path as an absent optional policy. This source fix is
based on `192b0df98644b845fd3117516ec9d42c4167acfa`.

Additional unchanged-source Linux reproductions retained two Python failures
and one native failure. They included a simulated Windows missing-entry error
for an invalid ancestor and a policy disappearing after a successful stat.
The latter could also select the absent-policy default after a failed read.

## Corrected boundary

[NativeTelemetryStore.company](../../studio/electron/telemetry-store.ts) and
[Python company_policy](../../mnemion/product_telemetry/policy.py) now distinguish
initial absence from a failed read of an observed file. An absent path checks
at most **32 ancestors** until the nearest existing entry is found; that entry
must be an actual directory. An invalid ancestor, symbolic link, unreadable
path or exhausted search denies permission. Once the policy file was observed,
disappearance or any failed read also denies. A later fresh check can establish
absence again.

The normal absent-policy default is unchanged and cannot enable an opted-out
user. There is no positive permission cache. Current user choice, company
restrictions, generation and final delivery checks remain required.

## Closed checks

| Scope | Result |
| --- | --- |
| Python policy selection | 22 passed. |
| Actual Electron runtime selection | 57 passed, two Windows-specific skips; no failures. |
| Electron build and Ruff | Passed. |
| Actual Windows x64 Node 25.2.1 | Both cold-start checks passed, with no skips. |
| Actual Windows x64 Python 3.13.11 | Six direct filesystem cases passed; the invalid ancestor actually returned errno 2. |

The Windows fixture copied **91 compiled files** and was removed afterward.
Original Windows logs, unchanged-source failures and corrected logs remain
retained. The private `company-path-qualification.json` receipt has SHA-256
`ed379481249781fba6a5e01656cd2310f046ff3fd8843cb549af2eab554bfdf2`.
No model calls occurred, and no resource measurement was selected.

At this checkpoint, the 4.46.32 source release driver was held before native
dispatch. The pending [4.46.31 native run 40417437026](https://github.com/Perseusxrltd/mnemion/actions/runs/40417437026)
was cancelled to avoid repeating the known defect; the original 4.46.30 run
was left intact. These source and Windows component checks do not qualify a
new installed/native release, Windows ARM64 execution, resources or production
privacy. The [existing resource failures](2026-10-27-telemetry-metadata-allocation-results.md)
and **2 MiB / 0.5%** gates remain unchanged. All 66 requirement texts and states
remain unchanged; V08 is Building, collection/destination/route are
**false/null/null**, and release CAs remain empty.
