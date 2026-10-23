# Release scan: OpenSSL public integrity constant

**23 October 2026 source-policy checkpoint.** The corrected full remote
verification remains pending. Current publication and release gates belong to
[release status](../RELEASE_STATUS.md).

## Retained rejections and corrected classification

[Publication verifier 39901894314](https://github.com/Perseusxrltd/mnemion/actions/runs/39901894314)
failed its possible-credential scan at **04:49:42 UTC**. The
[six native targets](2026-10-23-4460-native-acceptance.md) and exact
byte/signature/feed validation had passed for frozen product source
`a53ca6ff123c70686c8d89e2c9545143a2fadc37` in
[release run 39895069093](https://github.com/Perseusxrltd/mnemion/actions/runs/39895069093).
Those successes did not override the failed publication gate.

The local reproduction used the same **38 assets, 4,037,509,429 bytes** as the
rejected remote scan, with inventory SHA-256
`f101b56127a73ff8880d55f26655710c0afb17a1602a73ed6d28ad10ea05089d`.
It reproduced one `generic-api-key` finding in the Apple Silicon DMG. The binary
contains OpenSSL's complete published default FIPS module-integrity key, used
by `fipsinstall` as its default `hexkey` value. The scanner captured only its
first **38 hexadecimal characters**, not the full 64-character constant.

Primary OpenSSL source was accessed on **23 October at 05:06 UTC**, pinned to
commit `50b6c3085ac69129d6676f6c467bf2705fecec50`:

- [Configure](https://github.com/openssl/openssl/blob/50b6c3085ac69129d6676f6c467bf2705fecec50/Configure#L298)
  defines the default as SHA-256 of the public phrase
  `holy hand grenade of antioch`.
- [The generated-header template](https://github.com/openssl/openssl/blob/50b6c3085ac69129d6676f6c467bf2705fecec50/include/openssl/fipskey.h.in#L32)
  exposes that configured value as `FIPS_KEY_STRING`.
- [fipsinstall](https://github.com/openssl/openssl/blob/50b6c3085ac69129d6676f6c467bf2705fecec50/apps/fipsinstall.c#L845)
  uses it when no replacement key is supplied.

The full-value-only [policy revalidation 39905111700](https://github.com/Perseusxrltd/mnemion/actions/runs/39905111700)
failed at **05:24:38 UTC**, on the same DMG, line **46947**, and inventory.
Its expected policy and implementation hashes were confirmed. This report's
earlier claim that the complete scanner match equalled the full default was
inaccurate: it conflated the binary's full value with the truncated capture.
Both failed remote runs and the original inspection receipts remain preserved.

A public-only fixture reproduced that exact 38-character capture and entropy
**3.5986898** at a **125,000-byte scanner boundary**. Gitleaks source, accessed
23 October at 05:28–05:29 UTC and pinned to
`83d9cd684c87d95d656c1458ef04895a7f1cbd8e`, uses a
[100,000-byte buffer](https://github.com/gitleaks/gitleaks/blob/83d9cd684c87d95d656c1458ef04895a7f1cbd8e/sources/file.go#L21)
with up to [25,000 additional bytes](https://github.com/gitleaks/gitleaks/blob/83d9cd684c87d95d656c1458ef04895a7f1cbd8e/sources/common.go#L16)
while seeking a boundary. The earlier isolated **157-byte** line test did not
exercise this stream position and therefore missed the truncated capture.

## Narrow correction and rejection diagnostics

The revised [policy](../../.gitleaks.toml) anchors exceptions against the
scanner's `secret` value: only the exact full 64-character public constant and
its exact observed 38-character prefix are accepted. The exceptions cover no
other prefix length or value; filenames, OpenSSL components and `hexkey` lines
remain in scope. The [mandatory canary](../../deploy/secret_scan.py) retains the
fifth application-key placement beside the full constant and adds a sixth beside
the exact prefix. Existing binary, nested-archive, annotation-adjacent and
encoded-metadata controls remain required, including the nested vault-key control.

Rejected scans now retain a bounded `finding_summary`: validated rule IDs and
counts, input-asset SHA-256, archive-member-path SHA-256 and relative line
numbers, with at most **64 location entries**. The summary excludes matched
values, filenames and scanner descriptions. Maintainers can correlate the
asset hash with the verified inventory and inspect the corresponding bytes
privately. Truncation is explicit; diagnostics do not turn a rejection into
acceptance.

The [verification workflow](../../.github/workflows/verify-artifacts.yml) uses
scan policy from its pinned `github.workflow_sha` checkout. Product validation
continues to use the exact frozen release source, signatures and uploaded
bytes. This trusted policy-only correction needs no product rebuild; it still
requires a new successful scan of the complete unchanged inventory.

## Bounded verification and remaining gates

The initial full-value-only correction passed **15 focused source tests and
Ruff**. Its **05:09:03 UTC** source scan covered **1,736 files** with zero findings
and all five then-required controls passing. The isolated 157-byte line also
passed. At **05:10:48 UTC**, a separate real-scanner negative control correctly
rejected an application key beside the full public constant, retaining only
safe diagnostics. These narrower results did not cover the later boundary failure.

The revised correction passed **16 focused source tests and Ruff**, including
checks that other prefix lengths do not match the exceptions. At **05:31:44 UTC**, the product scan CLI
passed the public-only boundary fixture with zero findings and all **six**
mandatory placements detected by its canary. Corrected full remote verification
of the unchanged 38-asset inventory remains pending.

Source, generated desktop and downloaded-distribution gates retain their
coverage. ZIP/wheel/tar.gz/tgz expansion, flattened-byte inspection and decoding
remain bounded; filename exclusions and oversized-file skipping remain disabled.
Exhausted inspection limits prevent a passing receipt. Native executable
internals are not decompiled and encrypted content is not decrypted. A passing
scan applies to its recorded inputs and active rules.

The release remained draft at this checkpoint, with the actual Windows/shared
host pair accepted at [4.45.1](2026-10-23-4451-live-acceptance.md). Corrected full
remote verification, publication, public update checks and actual 4.46.0 paired
acceptance remain separate pending gates. No production host adoption or fresh
live-backup acceptance is claimed. All **65 requirement states** remain
unchanged; issues **#44/#45** remain open. The PC publisher pause and the
administrator conversation's stopped Grokbot/Adonis tests remain in force.
