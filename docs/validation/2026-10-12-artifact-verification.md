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
asset. With the corrected permission, the
[complete hosted check](https://github.com/Perseusxrltd/mnemion/actions/runs/38251760370)
passed at **12:53:05 UTC** against published 4.1.2, from exact source
`e01229febc0f791640365649a9653d51ae30b13e`. It downloaded and verified all **38
assets / 3,864,031,118 bytes**, including the production signature and package
checks. The [retained public receipt](2026-10-12-v412-hosted-verification.json)
matches every asset ID, name, size and digest from the independent local
prepublication inventory. Its checksum digest is
`9aed15835e4d662b1d1fc067042db0995bf8d46c16eaaea3b48481130825d7d6`.

This verifies manual dispatch and the complete hosted path against a public
release. The first [automatic draft verification](https://github.com/Perseusxrltd/mnemion/actions/runs/38260497593)
then passed at **14:07:56 UTC**, after the complete 4.1.3 release workflow.
It verified all **38 assets / 3,865,169,704 bytes** from source
`4465755e7119366baa58d5512e18ae58d80a9ba4`, while the release was still a draft.
The [receipt](2026-10-12-v413-hosted-verification.json) matched the unchanged
draft before publication; [public delivery checks](2026-10-12-v413-publication.json)
then confirmed the exact tag, asset inventory and anonymous update feeds.
The checksum digest is
`748a57ae4df2b6af5451fbe6aaf592b4c0f6bcacd75e0d27ff1d36e1dbb44073`.
Python lint, workflow YAML and shell syntax checks passed. The
[full product checks](https://github.com/Perseusxrltd/mnemion/actions/runs/38251655084)
on the corrected workflow also passed. The separate local 4.1.2 verification
preceded publication; the draft-discovery failure did not replace those checks.
