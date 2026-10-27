# Sparkle resource-metadata scan correction — 27 October 2026

The original [4.46.37 native build](https://github.com/Perseusxrltd/mnemion/actions/runs/40462412553)
passed. Its [artifact verifier](https://github.com/Perseusxrltd/mnemion/actions/runs/40468253346)
then rejected one `generic-api-key` finding in the macOS Intel disk image.
That failure blocked publication until the corrected verification below.
The original artifact and redacted rejection are retained; no release asset
was changed or rebuilt for this correction.

## Located public metadata

The downloaded disk image matched its verified size of **657,111,567 bytes**
and SHA-256
`f864e6e7443ec1e6cb418ce38d4c5ddfe34b9ef6a56a1b37bb21f1445c2f37bf`.
The reported line identifies this Sparkle resource-manifest key:

`PrivateHeaders/SPUAppcastItemStateResolver.h`

The complete line produces no finding. Terminating it after the exact
25-character text `PrivateHeaders/SPUAppcast` reproduces the original rule,
fragment-local columns **5–33** and entropy **3.863465**. This establishes the
public text responsible for the scanner-boundary match. The original complete
multi-asset input stream was not replayed locally.

The [official Sparkle 2.10.0 archive](https://github.com/sparkle-project/Sparkle/releases/download/2.10.0/Sparkle-2.10.0.tar.xz)
was checked against Mnemion's existing pinned distribution checksum. The
header's resource-manifest entry in the disk image equals the upstream entry.
This comparison does not claim that every resource-manifest entry is identical.

| Verified object | SHA-256 |
| --- | --- |
| Official Sparkle archive | `c2bf58aa8387266ac179357b1415d6f2635f044da8be41042af32425dae6da0c` |
| Upstream header, 1,105 bytes | `1c3be298008c19757ae3b27083622a005bce809a01f06d2c74f6dea16f3214ee` |
| Exact public fragment | `30d6fe7da913623af91458be12af4c55c483ff6804b81d7d07811f91427e4c6d` |

## Correction and checks

The [scanner policy](../../.gitleaks.toml) permits only that exact public
fragment. It excludes no files, path families or detection rules. The
[source tests](../../client_tests/test_secret_scan.py) reject every one-character
change, shorter and longer values, and appended text; all **41 tests passed**.

Actual pinned Gitleaks 8.30.1 rejects the fragment under the original policy
and accepts it under the corrected policy. It still detects an adjacent
synthetic Mnemion credential and a one-character neighbor through the generic
key rule. All existing canaries also pass: six application/backup-key findings,
one vault key, two Square-format keys and one generic key. No live credential
was tested.

Private evidence retains `upstream-qualification.json`,
`scanner-correction-checks.json`, the original rejected asset and the bounded
reproductions. The corrected policy has SHA-256
`c946f178327fd5cf2d5cd51d9c993c3fe99ccf81860b038c196ff5dbfe3e8ad1`.

## Completed verification and publication

The [corrected normal verifier](https://github.com/Perseusxrltd/mnemion/actions/runs/40473744894)
passed using verifier source `8c7d5847b778b2f2bf643edae98497d04aaba9cc`
and the reviewed scanner policy above. It checked all **38 original assets**,
totalling **4,067,021,212 bytes**, with **zero scan findings**. The
[artifact receipt](releases/4.46.37-artifacts.json) binds the unchanged asset
IDs, sizes and digests to original native run **40462412553** and release source
`629a7afc7938f87656ad05c2a38d5427ae5e35c8`. Its draft state records the
verification stage before publication.

[Mnemion 4.46.37](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.37)
was published at **2026-10-27T08:34:37Z**. The
[publication receipt](releases/4.46.37-publication.json) confirms that the tag
matches the verified release source and all 38 original assets remained
unchanged at publication. The original failed verifier and its evidence remain
retained.

The publication receipt preserves the initial follow-up dispatches. Later
retained release-observer evidence confirms
[website run 40474480217](https://github.com/Perseusxrltd/mnemion/actions/runs/40474480217)
completed successfully at **2026-10-27T08:35:19Z**, and
[public-updates run 40474484566](https://github.com/Perseusxrltd/mnemion/actions/runs/40474484566)
at **2026-10-27T08:46:37Z**. These normal release follow-ups do not establish an
installation upgrade on a particular PC or VPS. The earlier
[Electron metadata correction](2026-10-27-release-scan-boundary.md) remains
separate evidence.

This changes neither telemetry runtime nor its resource limits. V08 remains
Building; collection/destination/route remain **false/null/null**, with release
CAs empty. All 66 requirement states and remaining full acceptance gates are
preserved.
