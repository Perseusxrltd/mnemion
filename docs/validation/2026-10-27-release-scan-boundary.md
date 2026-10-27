# Release scan boundary correction — 27 October 2026

The original [4.46.29 native run 40403384477](https://github.com/Perseusxrltd/mnemion/actions/runs/40403384477)
passed, but
[artifact verification 40417189624](https://github.com/Perseusxrltd/mnemion/actions/runs/40417189624)
rejected one `square-access-token` match in the macOS x64 Electron Framework.
That rejection initially blocked publication and remains retained. The cause
was a scanner-boundary false positive in public upstream data. Corrected
verification subsequently passed, and 4.46.29 was published with its original
assets unchanged.

## Reproduction and provenance

Scanning the isolated member and its archive did not reproduce the rejection;
the exact original input prefix did. The complete raw line contains **zero
complete rule matches**. The scanner instead terminated a **48-character
Base64 fragment** at its boundary, while the next byte in the original line
continues the word. The retained match was raw input, without decode tags.

The fragment belongs to a complete **3,780,248-byte Base64 resource**, decoding
to **2,835,185 bytes of WebAssembly** with valid header and section bounds. The
entire encoded resource is identical to the one in the
[official Electron 44.9.3 macOS x64 archive](https://github.com/electron/electron/releases/download/v44.9.3/electron-v44.9.3-darwin-x64.zip),
whose published checksum was verified.

| Verified object | SHA-256 |
| --- | --- |
| Official Electron archive | `451363b59bb7d2c1c9e0c4baa99106004eaabe724aa21a0c6b4c87469293531a` |
| Decoded WebAssembly module | `79c79a0be6c92c7d8a1968cb1a7bed88737755d38d2b47ddfe4da5e51796a4e9` |
| Exact reviewed fragment | `0503a3e3ff318b5b861741387a30b3772a1678ec1d26bf9524df4dc773eb3f61` |

## Narrow correction and checks

The [scanner policy](../../.gitleaks.toml) permits only that exact reviewed
public fragment. No file or detection rule is excluded. Future
[rejection metadata](../../deploy/secret_scan.py) includes bounded
fragment-local columns and entropy, without matched values or filenames;
fragment columns are not presented as absolute positions in the original file.

All **40 source tests passed**. The actual pinned **Gitleaks 8.30.1** scanner
still rejects the fragment under the old policy and accepts it under the
corrected policy. It detected six Mnemion application/backup-key canaries,
one vault key, two Square canaries—including a one-character neighbor of the
reviewed fragment—and one generic-key match.

The private `release-44629-verification` evidence set retains the original
artifact, rejection, isolated checks, prefix reproduction, fragment/resource
proof and official-upstream qualification. `scanner-correction-checks.json`
has SHA-256
`7a93b0a47518cf2e7385dd1c37a3f0f30985af5eda48551e5da183300474a95d`.
No live credential validation was performed.

## Completed verification and publication

The corrected [verifier 40423232306](https://github.com/Perseusxrltd/mnemion/actions/runs/40423232306)
completed successfully using trusted workflow source
`da93e4c7163cded188bb00895ea6d0da27b08675`. It verified the original native
run's source `39ed946a58b8a4dd10da2dd8f4b88bc71582df12` and all **38 original
release assets**. Asset identities, sizes and digests remained unchanged after
verification and at publication; the release tag matched the verified source.
The full remote distribution scan passed with **zero findings**, using the
reviewed rules and no filename exclusions or file-size skips. Its recorded scope
does not include executable decompilation or encrypted-content decryption.

[4.46.29 was published](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.29)
at **2026-10-27T00:03:26Z**. The [publication receipt](releases/4.46.29-publication.json)
and [verified asset inventory](releases/4.46.29-artifacts.json) are committed
alongside this report. The retained publication evidence also includes
`qualification.json`, SHA-256
`fa79fd066d5c5f013e31d1408a970e22bdaac6d814e21e2499f80e015ca68f73`,
and `publication.json`, SHA-256
`13b1110f7d01144f869c189d6253fb9aeed039baa659f4ca7f8faa26d9522d8f`,
alongside the completed-verifier, release-verification and secret-scan receipts.
No full local distribution scan was repeated. The original failure and its
upstream provenance remain retained.

This qualifies publication of the original 4.46.29 artifacts, not the later
4.46.33 implementation or full telemetry. The correction changes no telemetry
policy, resource ceiling or requirement state. All 66 requirements remain
intact; V08 stays Building and production collection remains unavailable.
Telemetry resource, installed-platform and provider/privacy gates remain open.
