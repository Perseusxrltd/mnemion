# Complete product-check reuse — 20 October 2026

This record describes the locally verified CI reuse change. It does not claim
that a GitHub release has already reused Product checks successfully. Actual
GitHub reuse acceptance remains a separate release receipt.

## Reviewed source behavior

The [release workflow](../../.github/workflows/release.yml) uses
[`deploy.ci_reuse`](../../deploy/ci_reuse.py) to select only a successful,
completed, same-repository `main` push at the immutable release commit. The
job inventory must match the full static matrix in that commit's
[Product checks workflow](../../.github/workflows/ci.yml), with every required
job successful. Failed, skipped, foreign, incomplete or unavailable evidence
selects full release checks; a reduced documentation-only run cannot qualify.

Reuse also requires the same CI run's unexpired Intel runtime artifact and
GitHub digest. The transfer verifies the downloaded archive's SHA-256 and accepts
only bounded regular wheel files. If transfer or integrity validation fails
after selection, assembly stops. The selected lane, six native installer/runtime
targets and independent artifact/publication checks remain mandatory. No paid
runner or provider is introduced; all 65 product requirements remain in scope.

The existing frozen 4.40 and 4.41 candidates retain their original workflows.
This change does not cancel, rewrite or retroactively reuse their checks.

## Acceptance still to record

The focused reuse, artifact verifier, release status and release orchestration
group passed **144 tests**. Actionlint **1.7.12** passed on the three changed
workflows; pinned Ruff and the version/notes/roadmap validator passed. Seven
changed local documentation links resolve. These checks exercise exact-source
eligibility, incomplete and failed evidence, artifact boundaries and both
publication lanes; they do not substitute for GitHub execution.

The first real reuse receipt must identify the frozen
source, originating successful CI run, complete job inventory, selected artifact
and digest, successful transfer, all six native targets and independent
publication verification. A full-check fallback remains a valid release path;
it is not evidence that reuse itself ran. Actual installed versions and customer
workspace acceptance remain separate from publication.

## Public documentation review

An anonymous HTML read of the
[product page](https://www.perseusxr.com/mnemion) at **13:41:55 UTC** showed stable
4.39.0, all six matching installers, versioned guides and release notes, checksums
and the roadmap on `main`. No page version or download link needs a manual edit
for this CI change. The existing automatic website and public-update workflows
continue to manage release propagation.

Two static copy gaps were reported for separate website maintenance: the Mac
caption does not distinguish the macOS 13 desktop from local Apple silicon
workspaces requiring macOS 14, and the
first setup step mentions only an administrator-provided address/key without
describing personal sign-in or the app's native workspace setup. This was a text
and link review, not a new visual/browser acceptance run; no live page was changed.
