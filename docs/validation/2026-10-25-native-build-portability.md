# Native build portability correction

**Unreleased source checkpoint, 25 October 2026.** The unpublished
[4.46.7 candidate](../releases/4.46.7.md) is superseded by
[4.46.8](../releases/4.46.8.md). Local correction checks passed; native release
and installed acceptance remain pending. Public and installed **4.46.6** remain
the last verified baseline.
All 66 requirement texts/states are unchanged; V08 remains Building and
production collection/destination/route remain false/null/null.

## Original release failures

[Native release run 40234157718](https://github.com/Perseusxrltd/mnemion/actions/runs/40234157718)
exposed two build-environment failures:

| Surface | Observed failure |
| --- | --- |
| Windows | `uv run --no-sync npm --prefix studio/electron test` failed to spawn `npm`: `program not found`. npm was installed as a Windows command shim; this was a test-launch failure, not a passing native test run. |
| Ubuntu 22.04 Linux x64/ARM64 | Strict C11 compilation could not find `RTLD_DEFAULT` in the older glibc headers. The Node-API helper failed to build before native acceptance. |

The original Windows and Linux failure logs remain preserved. These failures do
not invalidate the prior installed 4.46.6 acceptance, and they do not establish
an installed backup-capture regression or correction.
At review, the old workflow was still running with four failed Windows/Linux
desktop jobs; it had not qualified a release or published 4.46.7.

## Source correction

The [Node-API helper](../../mnemion/product_telemetry/native/network-node.c)
defines `_GNU_SOURCE` on Linux before any header is included, exposing
`RTLD_DEFAULT` with strict C11 on the affected headers. It does not change the
network-cost policy or enable product collection.

The [native workflow](../../.github/workflows/desktop.yml) invokes npm through
the normal runner shell on every OS. It supplies `MNEMION_TEST_PYTHON` explicitly
from the locked service environment, including the Windows executable path, so
TLS fixtures retain their locked Python/cryptography dependencies. The
[source CI workflow](../../.github/workflows/ci.yml) uses the same separation of
the npm launcher and locked test interpreter. No release check is removed or
skipped by this correction.

The [managed backup-capture change](2026-10-25-host-backup-capture.md) is retained
in 4.46.8, including its existing source-test evidence. The prior naturally
completed ledger delivery remains separate from acceptance of an installed fix.

## Local validation and remaining gates

At **21:27:00 UTC**, the normal command
`npm --prefix studio/electron test` exited **0** on **Linux x64, Node 22.22.0**,
with explicit locked `MNEMION_TEST_PYTHON` and `MNEMION_BUILD_PYTHON` selections.
The corrected native network helper and TypeScript build completed.

| Local selection | Passed | Skipped |
| --- | --- | --- |
| Primary suite, 400 tests | 397 | 3 |
| Updater suite, 20 tests | 20 | 0 |
| Combined | **417** | **3** |

The three existing skips are Windows reader/file-permission cases on Linux;
this correction removes no checks. Workflow YAML parsing and whitespace checks
also passed. The saved receipt binds the exact three changed source files.
This is local source evidence, not Windows, Ubuntu 22.04 or macOS native
qualification. Those targets still require the GitHub release gates.

| Original evidence | SHA-256 |
| --- | --- |
| Windows release failure | `9e3f779999f2730411547eb0cf10112dbc926d14cfc5fd09cbc1101713462e37` |
| Linux release failure | `fbc89e424e3cdf9377ad13163c26169f322a30e963d8c3df3a2a6df854a31dfe` |
| Local validation receipt | `15b6b98866ae3725105771c8bee789537b258a89e404514c7f612accf4cc1998` |
| Normal npm command log | `19c33f3422ab65c1f1844944c321cd26ef5578616d2907c713f6ae64538f303b` |
| Source CI workflow | `d57c870ebca055809b4235d855ecbacc9ce0c090d3f53d42aab22a5e6b1b94cd` |
| Native desktop workflow | `522f418338f4906d14c7aadfd472d5d8c57b0c6411bb374f604a3eb914634bf3` |
| Native Node-API helper | `46df8b0914cbec3cd4ceb9cffdb096164317186b74bc48a85051c5066fd4f591` |

All-six-native, publication and actual installed 4.46.8 acceptance remain
pending, as do the full telemetry resource, platform and collector/ingress
privacy requirements. No installed backup fix or completed telemetry feature
is inferred from this checkpoint.
