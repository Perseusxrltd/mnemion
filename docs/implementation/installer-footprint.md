# Installer and update footprint

Quentin reported a downloaded installer of about 1 GB on 28 October 2026 and
requested a smaller distribution. This extends F05/F06 and the release/update
acceptance work; the original capabilities and platform scope remain required.
The exact reported filename/version remains unconfirmed. Its size must not be
confused with the installed application or optional downloaded models.

## Measured baseline

A release-metadata review on **29 October 2026 at 00:59 UTC** covered
**106 release records: 105 published releases and one draft**. It found
**886 published installer/archive assets**, none at or above **800,000,000
bytes**. The largest was the 4.46.44 Mac Intel disk image listed below.
This review downloaded no artifacts. The exact reported 1 GB file remains
unidentified; these metadata results do not establish which file Quentin saw.

GitHub's public **4.46.44** asset metadata, checked on 28 October at 17:26 UTC:

| Download | Bytes | Decimal MB |
| --- | ---: | ---: |
| Windows x64 installer | 226,799,860 | 226.8 |
| Windows ARM64 installer | 220,876,154 | 220.9 |
| Mac Intel disk image | 665,799,183 | 665.8 |
| Mac Apple Silicon disk image | 657,119,759 | 657.1 |
| Mac Intel update ZIP | 655,729,989 | 655.7 |
| Mac Apple Silicon update ZIP | 647,110,207 | 647.1 |
| Linux x64 AppImage | 266,740,086 | 266.7 |
| Linux ARM64 AppImage | 270,205,968 | 270.2 |

The earlier independently inspected Windows **4.46.42** installation contained
694,478,645 regular-file bytes across 3,827 files. Its local service accounted
for 196,086,159 bytes, PostgreSQL 76,970,796, the credential client 25,011,360,
and the desktop frontend 6,070,575. The Electron executable alone was
246,819,840 bytes. These are logical installed sizes, not installer downloads,
physical disk allocation or a measurement of other platforms.

A completed read-only traversal of the actual Windows **4.46.44** installation
on **29 October at 01:04 UTC** measured **694,611,545 logical bytes across 3,844
regular files**, excluding symbolic links. No files were changed. Its
`application` aggregate is **386,495,350 bytes across 73 files** outside the
`resources` groups. That aggregate is not a measurement of the Electron
executable alone; the executable size above belongs to the earlier 4.46.42
inspection. These installed totals are separate from the compressed downloads
and do not measure physical disk allocation or optional downloaded models.

Retained evidence is `summary.json`, `releases.json` and
`installed-windows-44644-footprint.json`. The release metadata SHA-256 is
`0347de6f9d5caf15731a2f1fb1b1c2b5a7328d5e7af59fc940feec01c4eff37d`;
the installed-footprint receipt SHA-256 is
`51370ac4138e41d9152c9b5245b176dd7cec45b4f2fbffc9257fe1e30999e193`.

## Immediate correction in 4.46.46 source

The desktop package selected `compression: store`. For Mac this makes the
packager use an uncompressed `UDRO` disk image and stored update ZIP entries.
Source 4.46.46 selects balanced lossless compression (`normal`), which uses
`UDZO` and compressed ZIP entries. No runtime component, model option, language,
license or recovery feature is removed. The Windows NSIS decoder's required
BCJ filter remains unchanged, as do signed update verification and all six
native installation/recovery gates.

The first corrected-source [native run](https://github.com/Perseusxrltd/mnemion/actions/runs/40757944923)
produced these **unpublished 4.46.46** archives:

| Download | Bytes | Decimal MB | Reduction from 4.46.44 |
| --- | ---: | ---: | ---: |
| Mac Apple Silicon disk image | 263,519,971 | 263.5 | 59.9% |
| Mac Apple Silicon update ZIP | 267,182,507 | 267.2 | 58.7% |
| Mac Intel disk image | 270,979,220 | 271.0 | 59.3% |
| Mac Intel update ZIP | 274,724,847 | 274.7 | 58.1% |

Apple Silicon passed its native installation/recovery checks. Intel's archives
built, but its installed workspace recovery check failed; Windows x64 also
stopped on a test-fixture timeout. The corrected candidate must pass the normal
native matrix before publication. These measurements describe those actual
archives, not a promise of identical byte counts for later builds.

At **01:36 UTC on 29 October**, the later **4.46.46-r2**
[native run](https://github.com/Perseusxrltd/mnemion/actions/runs/40793646583)
had completed successfully, including all six desktop targets. Its own installer
receipts record these exact sizes, separately from the first candidate above:

| Download | Bytes | Decimal MB | Reduction from 4.46.44 |
| --- | ---: | ---: | ---: |
| Mac Apple Silicon disk image | 263,523,493 | 263.5 | 59.9% |
| Mac Apple Silicon update ZIP | 267,186,562 | 267.2 | 58.7% |
| Mac Intel disk image | 270,983,940 | 271.0 | 59.3% |
| Mac Intel update ZIP | 274,728,858 | 274.7 | 58.1% |

Publication remained pending while the uploaded-artifact verifier ran. Native
success and these measured archive sizes do not substitute for its publication
receipt. Retained receipts are `native-44646-r2-macos-arm64-sizes.json` and
`native-44646-r2-macos-x64-sizes.json`; both bind their completed job logs and
source `21a2f377d3bf28585a8ba4ea8f0483798a639252`.

The [uploaded-artifact verifier](https://github.com/Perseusxrltd/mnemion/actions/runs/40801321439)
then passed, and [4.46.46 became public](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.46)
at **01:39:16 UTC**, with 38 assets. Published metadata matches the four Mac
sizes above. The Windows x64/ARM64 installers are **225,845,093 / 219,929,230
bytes**; Linux AppImage/deb packages range from **242,935,672 to 270,230,288
bytes**. The [automatic website synchronization](https://github.com/Perseusxrltd/mnemion/actions/runs/40801711006)
also passed its live download, version, guide and roadmap checks.

The existing installer verifier also records installed regular-file bytes and
component totals on each platform, alongside download bytes. The live
[product page](https://www.perseusxr.com/mnemion) displays sizes from the same
validated release assets as its download links, including the recommended
download and all platform choices. Future public releases update these values
through the existing Git-driven synchronization, without a page edit.

Source 4.46.48 adds a **400 MiB (419,430,400-byte) per-installer publication check**
in the [installer verifier](../../studio/electron/scripts/verify-installer.mjs).
It rejects enumerated installer/archive downloads larger than that limit and
records the budget in the verification receipt. This bounds download bytes,
not installed application size. The JavaScript syntax check passed locally;
the native gate on this new source remains pending. The earlier candidate runs
do not qualify this added check. Existing signature, payload, feature-parity
and native installation/recovery checks remain required.

## Further reduction and acceptance

After measuring the compressed artifacts, evaluate fetching the local service
and database only when a user creates or recovers a workspace on that device.
Team members using an existing host should not need to download an unused local
host. This remains implementation work, not a shipped lightweight installer.

Any such split must retain an offline installation route, authenticated runtime
manifests, resumable downloads, app and agent setup parity, version-compatible
atomic updates, safe rollback/forward recovery, and explicit disk/network status.
Models remain selected and prepared through the existing model controls. Do not
replace a large initial download with undisclosed mandatory background downloads.

Retain all working Windows, Intel/ARM Mac and Linux workflows. Compare actual
download and installed bytes, update transfer size, installation/restart behavior,
and resource use. A smaller archive alone does not close F05/F06 or the complete
roadmap. [Release status](../RELEASE_STATUS.md) identifies published artifacts.
