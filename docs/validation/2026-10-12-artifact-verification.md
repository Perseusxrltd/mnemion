# Independent release artifact verification — 2026-10-12

The [artifact verification workflow](../../.github/workflows/verify-artifacts.yml)
moves the complete post-upload byte and signature check onto a separate GitHub
runner. It runs after a successful **Prepare signed release** workflow, or when
an operator supplies that completed run ID. It does not publish or modify a
release, receive signing keys, or require a paid service. GitHub
[requires push access to list drafts](https://docs.github.com/en/rest/releases/releases#list-releases),
so the job needs `contents: write` and `actions: read`. Its code uses only
metadata reads and downloads; neither checkout persists credentials. The
release's source validator does not inherit GitHub API tokens.

The verifier requires the successful release workflow from the same repository,
all its completed gates and an unchanged checkout of its exact commit. It
downloads the expected draft or published version with three bounded workers.
It refuses unsafe names, links, duplicate IDs/names, missing digests, incomplete
uploads and oversized inventories. Limits are 128 assets, 2 GiB per asset and
8 GiB total; current complete releases fit within these limits.

Every file must match GitHub's exact size and SHA-256 digest. The verifier then
runs **that release commit's** existing production signature, feed and package
validator. The recomputed checksum inventory and all local bytes must remain
unchanged. A final GitHub read checks that the release and asset IDs, sizes and
digests did not change during verification. An already published tag must resolve
to the verified commit. Only a successful check writes the receipt.

The workflow retains a small JSON inventory and verification receipt for seven
days, avoiding another stored copy of all installers. Publication still requires
the matching draft review and completed gates. Public feed/relaunch rehearsals,
website reconciliation and actual user-device observations remain separate.

Twenty-nine local tests passed in a bounded 512 MiB / one-CPU scope. They cover
wrong or failed workflows, changed source, unsafe/incomplete metadata, altered
downloads, linked caches, validator failures, changed checksums/payloads, remote
asset replacement, exact public tags, digest-checked reuse, download bounds and
removing GitHub tokens from the source validator's environment.
These fixtures exercise orchestration, not real production signatures. The
first [hosted attempt](https://github.com/Perseusxrltd/mnemion/actions/runs/38249436257)
resolved the completed release and its source, but its `contents: read` token
could not discover the draft. It stopped before downloading or validating any
asset. The corrected permission and complete hosted check remain to be verified.
Python lint, workflow YAML and shell syntax checks passed. The separate local
4.1.2 verification checked all 38 assets and production signatures before that
release was published; the draft-discovery failure did not replace those checks.
