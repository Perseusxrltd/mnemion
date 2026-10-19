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
3. Run checks appropriate to the change, then commit reviewed source.
   `python -m deploy.release_automation integrate` pushes it normally to main,
   rebasing only incoming generated metadata; incoming source changes need review.
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
   From 4.24, `python -m deploy.binary_preflight` also checks binary-only locked
   dependency resolution for the current Python interpreter on all five service
   targets (the two Windows desktop architectures share the x64 service). It
   runs before local release dispatch and in the release workflow before native
   builders. Use pinned `uv==0.12.24`; `MNEMION_RELEASE_UV` can supply its path.
   This is a dry run: it installs nothing, starts no service and compiles no
   dependency. Intel cryptography is the sole exception because its signed wheel
   has a separate native build/inspection gate. Target floors are macOS 13 Intel,
   macOS 14 ARM and glibc 2.28 Linux. Native execution checks still decide delivery.
4. The release workflow runs product/native gates and creates a draft. The
   independent verifier checks the exact uploaded bytes, signatures, complete
   feeds and their unchanged inventory. GitHub can report the workflow completed
   before its job listing catches up. The verification workflow waits up to
   20 minutes for that listing, checking every 15 seconds and keeping the source
   commit and run attempt fixed. Every job must actually report completed/success;
   a failed gate or changed identity stops immediately. No asset is downloaded
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

`python -m deploy.maintenance_snapshot` reports the current published release,
new/updated/closed issues, changed builds and failed job steps as bounded JSON.
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
it. For a corrected version that has **never been published**, commit and push
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
