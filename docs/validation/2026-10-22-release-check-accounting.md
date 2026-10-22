# Release status recognizes the complete embedded check suite

Public **4.44.2**, source `3bdb3371ccd31bcf095d2e25a4b7d8263260b735`,
passed all **12 Product checks** inside
[release run 39753067641](https://github.com/Perseusxrltd/mnemion/actions/runs/39753067641).
The last check completed at **09:35:17 UTC on 22 October**, before publication
at 10:18:29 UTC. The 14:47 status snapshot incorrectly described Product checks
as **not recorded** because there was no separate standalone CI run.

The reporter now verifies the complete embedded suite against the CI workflow
at the immutable release commit. It checks the exact job inventory, matrix,
source, run, completion and successful steps. Missing, extra, skipped, foreign
or incomplete checks cannot qualify. Failed, running or manually cancelled
standalone checks are not replaced by older green evidence. The workflow uses
the existing pinned YAML parser to read the frozen matrix.

All **86** focused status and CI-reuse tests passed. An offline replay of the
original status snapshot, the recorded release jobs and the frozen workflow
correctly qualified all 12 checks and rendered the matching explanation.
This replay made no workflow dispatch, deployment or product change.

The additional [standalone run 39815622908](https://github.com/Perseusxrltd/mnemion/actions/runs/39815622908)
was started while investigating the missing status entry. Its first Intel Mac
dependency download timed out at PyPI. Its Python 3.14 runner reported no active
step or progress for 34 minutes and was cancelled after inspection. The single
failed-job retry retained the ten completed successes and retried those two
checks. These original attempts remain visible; they are separate from the
successful release suite. Future missing-status reconciliation uses existing
complete evidence without starting redundant validation.

Private receipts are retained in `2026-10-22-release-check-accounting/` and
`2026-10-22-shared-host-4442/`. This correction changes release reporting;
durable capture and the [remaining product requirements](../PRODUCT_REQUIREMENTS.md)
keep their own acceptance and publication gates.
