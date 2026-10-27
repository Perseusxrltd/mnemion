# macOS ARM runner capacity follow-up — 27 October 2026

Source [Product checks run 40524093039](https://github.com/Perseusxrltd/mnemion/actions/runs/40524093039)
at `62b9ab71e761a4e759e55d67ba9fc4e875e90eb8` failed both its original
attempt and the existing bot retry. The ARM jobs
[122258864987](https://github.com/Perseusxrltd/mnemion/actions/runs/40524093039/job/122258864987)
and [122275903785](https://github.com/Perseusxrltd/mnemion/actions/runs/40524093039/job/122275903785)
were cancelled before acquiring a runner or executing steps. Both retained
annotations state: “The job was not acquired by Runner of type hosted even after
multiple attempts”, with explicit macOS arm64 capacity notices. The other eleven
required checks, including Intel Mac, passed. Both failed attempts remain evidence.

The follow-up, based on `c14d80a166961ec19d3ae2968c99d35bcbeb3330`, selects
the standard `macos-26` ARM image listed in the official
[GitHub runner image catalog](https://github.com/actions/runner-images).
It replaces `macos-15` in source CI, desktop release selection, native database
defaults, installed-upgrade checks, the macOS updater probe and the diagnostics
default. Diagnostics retain `macos-15` as a manual option; Intel remains
`macos-15-intel`. No paid larger runner is selected. All six desktop targets,
five database builds (Windows ARM uses the x64 engine) and twelve required Product
checks remain. Deployment targets, build code and acceptance gates are unchanged.

The existing [database cache identity](../../deploy/native_database_cache.py)
includes the runner image, image version and hashed build instructions. Missing
image metadata refuses cache reuse. An old image's database cache therefore cannot
qualify as a build for the newly selected image.

The existing [CI reuse](../../service_tests/test_ci_reuse.py) and
[native database cache](../../service_tests/test_native_database_cache.py) suites
passed **65 tests, with no failures or skips**; Ruff check and format passed.
All 27 selected inputs were verified with digest
`63c5b6a2e370fa01263297c5477d250fed456b6ad59104042be1ff8d6d2a427f`.
The retained check receipt has SHA-256
`75d0ea007f28dde2958b0e8948f8393d5d89d4560c5e7aad10279f8ed35d3712`.
Separately, all 435 [collector-tested inputs](2026-10-27-telemetry-collector-crash.md)
still match, preserving that 21-pass qualification without rerunning it.

At this checkpoint the original 4.46.42 release driver and source-only collector
integration stopped before mutation; 4.46.42 had no remote release branch, tag or
native dispatch. The replacement handoff still requires successful current source
CI and the normal native gates. These local checks establish no runner-capacity
or macOS 26 compatibility success. [Release status](../RELEASE_STATUS.md) owns
subsequent availability.

All 66 requirement states remain unchanged. V08 is **Building**, production
collection/destination/route remain **false/null/null**, and release CAs remain
empty. The [failed resource comparison](2026-10-27-telemetry-sql-comparison.md),
unchanged 2 MiB / 0.5% ceilings and remaining installed, wire, provider/privacy
and full telemetry acceptance remain open.
