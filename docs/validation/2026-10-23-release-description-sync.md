# Git-owned public release descriptions

Recorded **23 October 2026**. The published 4.46.3 GitHub description still
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
without writing. Public delivery of this correction remains a separate workflow
and API-readback check at this source checkpoint.

See [the documentation contract](../website/README.md) and
[maintenance instructions](../MAINTENANCE.md#automatic-product-page-updates).
