# Release scan: OpenSSL public integrity constant

**23 October 2026 source-policy checkpoint.** The corrected full remote
verification remains pending. Current publication and release gates belong to
[release status](../RELEASE_STATUS.md).

## Retained rejection and exact classification

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
It reproduced one `generic-api-key` finding in the Apple Silicon DMG. The
matched value is OpenSSL's published default FIPS module-integrity key, used
by `fipsinstall` as its default `hexkey` value. It is not an application
credential.

Primary OpenSSL source was accessed on **23 October at 05:06 UTC**, pinned to
commit `50b6c3085ac69129d6676f6c467bf2705fecec50`:

- [Configure](https://github.com/openssl/openssl/blob/50b6c3085ac69129d6676f6c467bf2705fecec50/Configure#L298)
  defines the default as SHA-256 of the public phrase
  `holy hand grenade of antioch`.
- [The generated-header template](https://github.com/openssl/openssl/blob/50b6c3085ac69129d6676f6c467bf2705fecec50/include/openssl/fipskey.h.in#L32)
  exposes that configured value as `FIPS_KEY_STRING`.
- [fipsinstall](https://github.com/openssl/openssl/blob/50b6c3085ac69129d6676f6c467bf2705fecec50/apps/fipsinstall.c#L845)
  uses it when no replacement key is supplied.

The complete matched value equals that public default. The original failed
receipts and inspection evidence remain preserved; this classification does
not rewrite the rejected scan as a pass.

## Narrow correction and rejection diagnostics

The [policy](../../.gitleaks.toml) adds one anchored exception against the
scanner's complete `secret` value. It accepts only this exact public constant;
other values, filenames, OpenSSL components and `hexkey` lines remain in scope.
The [mandatory canary](../../deploy/secret_scan.py) adds a fifth application-key
placement beside that constant. All existing binary, nested-archive,
annotation-adjacent and encoded-metadata controls remain required, including
the nested vault-key control.

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

**15 focused source tests and Ruff passed.** The **05:09:03 UTC** source-snapshot
scan covered **1,736 files** with zero findings and all five mandatory controls
passing. The exact **157-byte** binary line from the rejected asset also scanned
successfully. At **05:10:48 UTC**, a separate real-scanner negative control
correctly rejected an application key beside the public constant and retained
only the safe diagnostic fields above. These results do not qualify the full
38-asset remote scan.

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
