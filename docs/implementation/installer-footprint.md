# Installer and update footprint

Quentin reported a downloaded installer of about 1 GB on 28 October 2026 and
requested a smaller distribution. This extends F05/F06 and the release/update
acceptance work; the original capabilities and platform scope remain required.
The exact reported filename/version remains unconfirmed. Its size must not be
confused with the installed application or optional downloaded models.

## Measured baseline

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

The independently inspected Windows **4.46.42** installation contains
694,478,645 regular-file bytes across 3,827 files. Its local service accounts
for 196,086,159 bytes, PostgreSQL 76,970,796, the credential client 25,011,360,
and the desktop frontend 6,070,575. The Electron executable alone is
246,819,840 bytes. These are logical installed sizes, not installer downloads,
physical disk allocation or a measurement of other platforms.

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

The existing installer verifier also records installed regular-file bytes and
component totals on each platform, alongside download bytes. The live
[product page](https://www.perseusxr.com/mnemion) displays sizes from the same
validated release assets as its download links, including the recommended
download and all platform choices. Future public releases update these values
through the existing Git-driven synchronization, without a page edit.

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
