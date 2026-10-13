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
3. Run checks appropriate to the change, then commit and push reviewed source to
   main. `python -m deploy.release_automation start` freezes its `release/X.Y.Z`
   branch and starts the complete release workflow once. Existing matching runs
   are reported, not repeated; a different frozen source is rejected.
4. The release workflow runs product/native gates and creates a draft. The
   independent verifier checks the exact uploaded bytes, signatures, complete
   feeds and their unchanged inventory.
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
