# Automated release pipeline

Implementation and release notes still need engineering judgment. The mechanical
release steps use `deploy/release_automation.py` and the existing GitHub Actions
gates; no paid service, model call or new signing credential is required.

1. Implement a coherent batch, update the affected guides and write
   `docs/releases/X.Y.Z.md`. Keep unfinished product requirements visible.
2. Run `python -m deploy.release_automation prepare X.Y.Z` in the locked project
   environment. It updates the Python/npm packages, project lock entries, release
   targets and reviewed-source marker, generates OpenAPI and agent contracts, and
   validates the version boundaries. Unrelated dependency pins are preserved.
   It accepts both the original combined roadmap header and the current separate
   source/public-status lines, retaining the live public-availability link.
3. Run checks appropriate to the change, then commit reviewed source.
   `python -m deploy.release_automation integrate` pushes it normally to main.
   Incoming commits containing only allowlisted generated metadata are merged
   into the reviewed source, preserving resolved hotfix merges. Incoming source
   changes need review; the clean-worktree, repository and source checks still apply.
   It also fast-forwards a clean local main worktree. It never stashes user work,
   force-pushes or rebases a frozen release branch.
   `python -m deploy.release_automation start` freezes its `release/X.Y.Z`
   branch and starts the complete release workflow once. Existing matching runs
   are reported, not repeated; a different frozen source is rejected.
   From 4.15.0, the command first runs the pinned Ruff format/lint checks locally,
   before reserving that branch. This catches cheap failures without starting
   native builders. Use the locked development environment; it includes Ruff.
   From 4.22.0 it also runs focused PostgreSQL migration and installed-inventory
   checks using `python -m deploy.migration_preflight`. A successful local receipt
   is cached under ignored `build-tmp/` for the same source, schema, test, lockfile
   and Python/platform inputs. Changed inputs rerun the group; skipped database
   checks cannot pass. PostgreSQL or the development `pgserver` fixture must be
   available. These early checks do not replace the complete release gates.
   From 4.31, `python -m deploy.client_preflight` runs the small desktop bridge's
   tests in its own locked Python 3.13 environment. This catches engine-only
   tests or dependencies accidentally entering the lightweight bridge. Its
   receipt is reused only for identical relevant files and runtime. Native
   platform checks remain separate; install Python 3.13 before release start.

   From 4.24, `python -m deploy.binary_preflight` also checks binary-only locked
   dependency resolution for the current Python interpreter on all five service
   targets (the two Windows desktop architectures share the x64 service). It
   runs before local release dispatch and in the release workflow before native
   builders. Use pinned `uv==0.12.24`; `MNEMION_RELEASE_UV` can supply its path.
   This is a dry run: it installs nothing, starts no service and compiles no
   dependency. Intel cryptography is the sole exception because its signed wheel
   has a separate native build/inspection gate. Target floors are macOS 13 Intel,
   macOS 14 ARM and glibc 2.28 Linux. Native execution checks still decide delivery.
4. The release workflow requires complete product-check evidence, runs the native
   gates and creates a draft. Its preflight can reuse a completed full CI matrix
   for the same immutable source under the [rules below](#reusing-complete-main-ci-for-a-release);
   otherwise it runs the full Product checks workflow. The
   independent verifier checks the exact uploaded bytes, signatures, complete
   feeds and their unchanged inventory. GitHub can report the workflow completed
   before its job listing catches up. The verification workflow waits up to
   20 minutes for that listing, checking every 15 seconds and keeping the source
   commit and run attempt fixed. Every required gate must report completed/success;
   only the unused, mutually exclusive product-check lane may be skipped.
   A failed gate or changed identity stops immediately. No asset is downloaded
   until these gates pass. The standalone verifier defaults to no waiting;
   `--wait-seconds` opts into a bounded wait, at most 1,200 seconds.
5. A dependent publication job verifies the successful verification job, original
   release gates, main ancestry, unchanged asset IDs/sizes/digests, existing tag
   and latest stable version. It publishes only the matching release. A newer
   stable version or changed evidence stops publication.
6. Website and all-platform public update workflows are dispatched explicitly.
   This is necessary because GitHub's automatic token does not generate another
   release-triggered workflow. Existing matching full checks are reused, including
   failures, so a retry does not blindly restart expensive work.
7. Publication and verification receipts are committed under
   `docs/validation/releases/`. Status reconciliation retains each version's
   observed gates, targets and scope counts there and refreshes
   [current release status](../RELEASE_STATUS.md). The website continues to read
   the published release and current roadmap automatically.

The status reporter also recognizes a complete Product checks suite executed
inside the release workflow when no standalone CI run exists. It reads the CI
matrix from that exact release commit and verifies every matching job and step;
a successful parent workflow or a passing subset is insufficient. It does not
start a duplicate run to populate the status page. Failed, pending or manually
cancelled standalone checks retain their own outcome. The
[4.44.2 reporting correction](../validation/2026-10-22-release-check-accounting.md)
records the actual release evidence and the original additional attempts.

`python -m deploy.maintenance_snapshot` reports the current published release,
new/updated/closed issues, changed builds and failed job steps as bounded JSON.
Active builds also report completed/successful job counts and the current steps
of pending jobs. This uses the same bounded job response as failure detection;
a step change is reported even when GitHub's enclosing run timestamp is unchanged.
Unchanged successful polls remain silent, with no extra API request per job or step.
During a timed watch, failed or invalid reads emit `observation: unavailable`,
the last successful observation time and a bounded retry delay. The previous
complete inventory stays intact: a failed read cannot imply issue closure or a
passing build. Retries back off to at most five minutes and remain within the
requested watch period. Recovery emits a fresh `available` observation even if
the inventory is unchanged. Ending during an outage exits nonzero. One-shot
reads, including the generated-board CI job, still fail without replacing the
saved inventory. Raw command errors and response bodies are not printed by the
watch loop.
The existing status workflow refreshes the
[maintenance board](../MAINTENANCE_STATUS.md) on issue/comment changes, completed
release workflows and its schedule. It reads trusted code from main; issue text
is data only, never a command. Unchanged observations do not rewrite the board.
Failed job details are reused until that attempt changes. The script starts no
builds, sends no messages and makes no feature-completion decisions.

For a completely addressed issue, add its number to the reviewed version entry
in `deploy/issue-releases.json`. The status workflow runs
`python -m deploy.issue_releases --apply` after publication reconciliation. It
requires passing public release evidence and a matching GitHub release before
adding a `fixed-in:X.Y.Z` label with the download URL and closing an open report.
Already labeled reports that a user reopens stay open. No comments or other
messages are posted. Without `--apply`, the command only reports eligible and
pending associations. Engineering review still determines whether the fix is
complete; issue text cannot authorize a release or close a requirement.

For CI or a deliberate initial refresh, `python -m deploy.maintenance_snapshot --write`
updates the generated JSON and Markdown. Normal local inspection is read-only.
GitHub issue listing paginates up to 1,000 open issues; reaching that cap stops
before replacing the saved inventory, so truncated results cannot mark issues closed.

The verification job remains read-only and receives no signing secrets. The
separate publication job has repository write and workflow-dispatch permission,
with serialized publication to prevent overlapping releases. Manual artifact
verification dispatches remain read-only. No package is rebuilt after verification.

When a gate fails, inspect that run and fix its concrete cause. A failed full run
is not an invitation to bypass it or repeatedly exercise unrelated passing gates.
Re-run the failed workflow only when a fix or resolved transient error justifies
it. The status workflow makes one exception automatically: a completed first
attempt can receive one failed-job retry when its complete, bounded job inventory
contains only successes, skips or unstarted failures with the exact GitHub hosted
runner-capacity annotation. Each failed/cancelled job must have zero steps and no
assigned runner; other failure annotations or incomplete evidence refuse retry.
This requires our repository and either the current public release tag, an
unpublished frozen release branch still on main, or the latest eligible Product
checks push to `main`.

For source CI, the run commit must equal current `main`, or a bounded comparison
must show only paths accepted by the existing `ci_scope.documentation()`
classification. Its documentation/metadata scope does not include the separate
diagnostic-only exemption. The exact run commit must be both comparison base and
merge base, with one to 299 files and both names of a rename checked. Source
changes, missing/truncated comparisons, another branch/event and any newer main
push CI refuse retry. Immediately before the request, the helper rereads run
identity and repeats source eligibility. A capacity retry does not make a failed
or incomplete suite reusable as passing release evidence.

Actual test failures, timeouts, ordinary cancellations, forks, stale versions
and second attempts remain for investigation. Passing jobs and release assets
are reused; no paid runner or check bypass is added. Inspect without mutation
using `python -m deploy.runner_capacity_retry --run RUN_ID`; `--apply` enables the
same bounded action used by the workflow. Its separate job has Actions write
permission but no repository-content or issue write permission.

The [4.46.24 source follow-up](../validation/2026-10-26-telemetry-capture-actions.md#source-ci-capacity-recovery)
passed 41 guard tests using mocked GitHub reads and mutations. Those tests do not
establish runner availability, an actual retry or native release qualification.

For a corrected version that has **never been published**, commit and push
the fix to main, then use `python -m deploy.release_automation start --attempt 2`
(or the next attempt number). This freezes a separate `release/X.Y.Z-r2` branch;
the failed attempt's source is preserved. A published version requires a new
version number. Immutable public assets and source branches are never overwritten.

To inspect a real receipt without publication or dispatch, use:

```sh
python -m deploy.release_automation publish \
  --repo Perseusxrltd/mnemion \
  --verification-run RUN_ID \
  --receipt PATH_TO_VERIFIED_RELEASE_RECEIPT \
  --dry-run
```

No download or profile diagnostic is treated as proof that a customer's actual
installation or independently hosted workspace has upgraded. Provider access,
customer-specific migrations and unfinished features keep their own evidence.

## Reusing complete main CI for a release

Release preflight uses `python -m deploy.ci_reuse` to look for an already completed
**Product checks** run. Reuse requires the same repository, a `push` to `main`,
the exact release commit and `.github/workflows/ci.yml` from that checkout.
The latest matching run must be successful. Its complete job inventory must
match every job and matrix target expanded from the checked-out CI workflow;
each required job must have completed successfully, with no failed steps.
An older successful run cannot override a newer failed or unfinished run.

This includes the service Python matrix, both Mac supervision targets, both
container targets, legacy checks, lint, dependency audit and Studio checks.
A successful documentation-only push has skipped runtime jobs and does not
qualify. Foreign repositories, another branch or commit, pull requests, manual
runs, skipped or failed required jobs, incomplete API inventories, unavailable
evidence and unsupported matrix syntax all select the ordinary full release
checks. Preflight does not wait for an unfinished CI run or infer acceptance
from a successful subset.

The selected CI run must also retain exactly one unexpired
`release-service-macos-x64` artifact, with a GitHub SHA-256 digest and matching
run/source identity. It contains the Intel cryptography runtime wheel built
with static OpenSSL and exercised by that run's Mac supervision checks.
The release downloads that exact artifact, verifies the archive bytes against
GitHub's digest, accepts only a bounded inventory of regular wheel files, and
transfers those unchanged wheel bytes into the release's own staging artifacts.
This preserves the tested runtime instead of recompiling it during reuse.
An absent or unverifiable artifact at selection time runs full checks. A failed
download or digest mismatch after selection stops the chosen lane and prevents
assembly; it never substitutes an unverified wheel.

The `product-check-reuse-selection` artifact retains the decision, reason and,
when eligible, source run and runtime artifact identity for 14 days. Runtime
transfers retain their existing one-day limit. A release assembles only when
preflight, all native gates and exactly one product-check lane have succeeded;
the unselected lane is expected to be skipped.

Independent verification reloads the CI job contract from the immutable release
commit. For the full-check path, every expanded check must have passed. For the
reuse path, it also rechecks the original main CI evidence and required artifact.
Only the unused complete check lane may be skipped; a skipped native,
assembly or other required gate still prevents publication. The verifier and
publisher install the pinned contract reader before resolving this evidence.

All six native desktop installer/runtime gates still run for the release:
Windows, macOS and Linux, each on x64 and ARM64. Their installed application,
recovery and update checks retain their existing platform contracts, including
the documented Windows ARM service emulation. Independent uploaded-byte and
signature verification, publication checks, website synchronization and all six
public-feed update checks also remain required. This uses the existing free
pipeline and does not add a paid runner, service or model call. It changes no
feature requirements or completion counts.

See the [validation record](../validation/2026-10-20-product-check-reuse.md) for
the distinction between source implementation and observed GitHub reuse.

## Reusing product-check evidence after a superseded branch push

When a release runs the complete Product checks workflow at its frozen source,
a newer main push can cancel that commit's separate branch CI without affecting
the release's checks. Status reconciliation
uses the successful release invocation when the standalone push was cancelled
and contained no failed job or step.

Both complete GitHub job inventories must identify the same source. Every
standalone job name must match exactly one successful reusable release job,
including every matrix target. Missing pages, mismatched identities, skipped
release checks, actual failures, pending checks and manually dispatched
cancellations do not qualify. The status record links the passing release
invocation and retains the cancelled branch run as separate evidence.

On 19 October, all eleven reusable checks for 4.24 passed in release run
39307882234; standalone push run 39307840806 had been superseded. Live collection
then recognized all five release gates, including six public installed updates.
The focused status suite passed 34 checks. This reads existing evidence and
does not rerun tests, alter artifacts or relax public-update requirements.

## Documentation-only push checks

`deploy.ci_scope` compares the exact before/after commits for ordinary branch
pushes. Changes limited to root/documentation Markdown, reviewed release/issue
status metadata and generated release evidence keep the lint and Studio jobs.
The allowlist includes flat, dated JSON acceptance reports under `docs/validation/`;
other JSON schemas, nested fixtures and unrecognized files still select runtime checks.
Studio still builds and verifies the packaged offline guides and runs its client
and desktop checks. The service Python matrix, native Mac supervision, containers,
legacy suite and Python dependency audit are reserved for runtime changes.

Every release requires the complete suite, either as eligible same-source
evidence under the reuse rules above or a new full invocation. Pull requests and
manual Product checks runs execute the complete suite. Unknown
paths, changed API schemas, workflow/dependency changes, a missing shallow-history
base or a mismatched checkout also keep all checks. Rename detection is disabled
when listing changes, so moving a source file into a documentation path still
counts its removed runtime path. There is no network lookup or cached acceptance
decision in this selection.

Thirteen focused checks passed, including a real Git documentation push and
source rename. The 20 October documentation-only main push selected the reduced
scope; the same source with the release flag selected the full suite. Existing
frozen release workflows retain their original checks.

The [22 October correction](../validation/2026-10-22-dated-evidence-ci-scope.md)
adds dated JSON reports to this classification. Its real six-file documentation
diff selected the documentation checks, while the same input selected every
runtime check when evaluated as a release. This avoids re-running the service
matrix merely to publish its already qualified evidence.
