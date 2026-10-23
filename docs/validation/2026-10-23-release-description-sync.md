# Git-owned public release descriptions

Original source checkpoint, **23 October 2026**. The published 4.46.3 GitHub description still
contained its original `UNRELEASED` source-checkpoint wording after publication.
The website synchronization workflow updated downloads and product text but did
not copy subsequent release-note corrections from Git to that description.

The source correction synchronizes the latest stable public release's Markdown
from `docs/releases/<published-version>.md`, after the workflow has committed and
pushed its documentation snapshot. Preparing a newer version does not select
its unreleased notes. Each write rechecks the identified public release and
sends only the `body` field; tags, assets and publication state are retained and
checked in the response. Repeating the same synchronization makes no write.

Links to newly added evidence use the documentation commit, since those files
may not exist in the older immutable release tag. Current roadmap, requirements
and generated status links still use `main`. The original draft renderer retains
its version-tag links. Git remains the source of corrections and dated acceptance
claims; this automation does not invent validation results or edit app binaries.

The focused selection passed **58 tests in 6.18 seconds**, covering the new
description boundaries and existing website content/download verification.
Checks cover a published version while a newer draft's notes exist, body-only
mutation, unchanged assets/tag, idempotence, preview and uncommitted-source
refusal, draft/prerelease/wrong-origin rejection, concurrent release changes,
and missing post-publication links. Ruff checks passed for the changed Python.
An actual API-backed preview selected 4.46.3 and proposed its corrected body
without writing. Public delivery still required a separate workflow and
API-readback check at that source checkpoint.

## Completed workflow and public readback

[Website synchronization 39977648980](https://github.com/Perseusxrltd/mnemion/actions/runs/39977648980)
completed successfully on main revision
[`49cde25079a342be8f26100a3d7ab5318f58b769`](https://github.com/Perseusxrltd/mnemion/commit/49cde25079a342be8f26100a3d7ab5318f58b769).
The actual published **4.46.3 release description was synchronized**, confirmed
by the separate readback recorded at **15:49:44 UTC**. Its original stale
description is a resolved historical checkpoint, not the current public text.

The workflow's `public-website-verification` artifact **12511064508**, created
at **15:22:29 UTC**, binds that run and revision. Its archive SHA-256 is
`4086b1711ad4c2b0678d86b22fe2f8b9ce72cb073352b7cefdecff8280d1aaf3`.
The decoded receipt at **15:22:28 UTC** verifies anonymous public HTML:
current version and release notes, all **six installer links**, **five guide
links**, checksums and Git-owned product/homepage/lab/download text. Script,
style and template text are excluded from the visible-content check. No website
code/deployment change or new visual render is claimed.

The 15:49 inspection still recorded main CI at 11 of 12 jobs. That same
[source CI run 39977648923](https://github.com/Perseusxrltd/mnemion/actions/runs/39977648923)
subsequently completed successfully at **15:50:41 UTC**, with **12 jobs passed**.
These documentation/workflow results belong to main revision `49cde250`; they
do not rebuild or change frozen 4.46.3 source `56e29f2c`. The later legacy
vendor-telemetry correction on main remains excluded from that release, and
V08 product telemetry remains Planned and inactive.

The saved artifact metadata, decoded receipt and dated readback retain the
original evidence. The separate [actual 4.46.3 paired acceptance](2026-10-23-4463-live-acceptance.md)
has its own deployment scope. The later
[two-custodian journey](2026-10-23-4463-custody-acceptance.md) passed separately
at 16:25:34 UTC; fresh backup and independent restore remained pending then.

See [the documentation contract](../website/README.md) and
[maintenance instructions](../MAINTENANCE.md#automatic-product-page-updates).
