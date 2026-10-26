# Release scan boundary correction — 27 October 2026

The original 4.46.29 native run passed, but
[artifact verification 40417189624](https://github.com/Perseusxrltd/mnemion/actions/runs/40417189624)
rejected one `square-access-token` match in the macOS x64 Electron Framework.
That rejection blocked publication and remains retained. The cause is now
established as a scanner-boundary false positive in public upstream data.

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

Full remote verification of the original **38 release assets** and release
qualification remain pending. No full local distribution scan was repeated;
these focused checks do not establish publication. The correction changes no telemetry policy,
resource ceiling or requirement state. All 66 requirements remain intact;
V08 stays Building and production collection remains disabled. Existing
resource, platform and provider/privacy gates remain open.
