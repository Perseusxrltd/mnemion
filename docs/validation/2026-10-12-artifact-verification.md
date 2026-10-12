# Independent release artifact verification — 2026-10-12

The [artifact verification workflow](../../.github/workflows/verify-artifacts.yml)
moves the complete post-upload byte and signature check onto a separate GitHub
runner. It runs after a successful **Prepare signed release** workflow, or when
an operator supplies that completed run ID. It does not publish or modify a
release, receive signing keys, or require a paid service. Its token has only
repository and Actions read permissions; neither checkout persists credentials.

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

Twenty-eight local tests passed in a bounded 512 MiB / one-CPU scope. They cover
wrong or failed workflows, changed source, unsafe/incomplete metadata, altered
downloads, linked caches, validator failures, changed checksums/payloads, remote
asset replacement, exact public tags, digest-checked reuse and download bounds.
These fixtures exercise orchestration, not real production signatures. The
first complete hosted artifact verification remains pending. Python lint,
workflow YAML, shell syntax and read-only-permission checks passed.
