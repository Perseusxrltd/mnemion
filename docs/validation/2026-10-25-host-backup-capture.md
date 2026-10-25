# Managed host backup capture under source contention

**Source hotfix checkpoint, 25 October 2026; source checks passed, unreleased.**
Scheduled snapshot and access-ledger captures repeatedly encountered
`host_operation_busy`. The proposed source correction gives managed captures a
bounded turn through the existing operator lock. Release/platform CI and an
actual installed correction remain pending. All 66 requirement
texts/states remain unchanged; V08 remains Building with collection unavailable.

## Observed scheduled jobs

The snapshot started at **03:21 UTC** failed after **32 retries**; recent ledger
jobs also reported the busy condition. The **20:55:11 UTC** read-only inspection
covered ten recent capture receipts, including **six verified nonmutating busy
refusals**: exit **75**, with no artifact, plan or artifact receipt. The active
host remained **4.46.6**. These failures did not capture or deliver a new copy.

The existing **20:30** ledger job subsequently completed naturally at **20:35**.
Its remote Git delivery was verified at **20:41:55 UTC**, carrying the **24 October
snapshot and 25 October ledger**. This did not create a 25 October full snapshot
or demonstrate the source hotfix. An independent GitHub manifest read matched
the delivered metadata and hashes for **three ciphertext files, 821,088,092
bytes**. That read downloaded no plaintext and requested no new capture or
publication. No live job was replayed, service paused, app
upgraded or host edited to obtain that observed recovery. The earlier failures
remain preserved.

## Source correction

For a managed host without a borrowed controller lease,
[host-package capture](../../mnemion/service/host_package.py) now requests the
existing [operator lock](../../mnemion/service/update_state.py) with a
**300-second acquisition window**. Existing scans can finish naturally; the
existing coordination mechanism prevents new scans from taking the pending
capture's turn. The five-minute bound applies to lock acquisition, not the whole
database/encryption job. An already-held controller lease remains borrowed.

After acquiring the lock, capture rereads protected settings and credentials,
refuses a changed management mode or a change in the complete active runtime
record across the wait, and rechecks snapshot/package-plan destinations so a
file created while it waited is preserved. Stable compatible older runtime
records remain allowed; the CLI version need not match them. The source change
does not introduce a scheduler, transfer replay, service stop/start or a new
backup destination.

The [focused capture tests](../../service_tests/test_host_capture_turn.py) use real
PostgreSQL and encrypted artifacts with simulated coordination time. They cover
a scan completing after 75 seconds, the 300-second refusal, settings/runtime
changes, a borrowed lease and a destination created during the wait. The initial
run had **six fixture failures and 11 existing passes** because exclusive JSON
publication could not replace its existing settings file. Atomic fixture updates
corrected that error; the six new cases first passed in **14.07 seconds**.
After the final runtime-record compatibility refinement, **all six new tests
passed in 12.45 seconds**. The borrowed-lease test uses an unchanged **4.46.5**
runtime record, preserving compatible older-host behavior.

Targeted verification therefore records **17 passes across retained logs**:
the final six new cases plus the 11 unchanged existing passes. It is not a claim
that the original combined run passed; its fixture failures remain preserved.

## SHA-256 provenance

| Original evidence | SHA-256 |
| --- | --- |
| Read-only host inspection | `76b5e7876863c0d1f04ef86b4348b5d4edce981a8a82761a298b99984d0af405` |
| Independent remote manifest comparison | `059a1e21fb0c2f20ed11caa44ce7bae50eb2cbaeeefbfe05fb65a8c556f25dbb` |
| Original combined test run, including fixture failures | `da329c02cb9a1bea8bc1f8c2b64a27c105f78b35ed0f1f35654727ec16349f0e` |
| First corrected six-case selection | `227a4ec1853117c79848f0f259626fe1f4960c06174c6e040d3d6918935650aa` |
| Final six-case selection | `c93bb1a63f5e02c1ed61d2f5aedadb795503379aedb6cd79a17c028628a921c6` |
| Reviewed host-package source | `09fadb27214454b6cfdefc3b1d2e52d94ff65a7b8e041bbd8fe7ba23d4a9c854` |
| Final capture tests | `f2072415d3c57c07a6f988916fbf6af128e2e1c21797123a5ce4556a4de33dc0` |

The [4.46.7 source candidate](../releases/4.46.7.md) still needs release/platform
and actual installed-correction acceptance.
The naturally successful ledger and prior independently accepted backup/restore
evidence do not qualify this new contention path, a fresh full snapshot or a new
restore. Product telemetry collection, production ingress and collector-entrypoint
qualification remain pending.
