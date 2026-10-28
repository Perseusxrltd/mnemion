# Exact release scan: complete public OpenSSL literal

The [4.46.42 native release](https://github.com/Perseusxrltd/mnemion/actions/runs/40540729543)
passed its platform builds. Its original
[uploaded-artifact verification](https://github.com/Perseusxrltd/mnemion/actions/runs/40550326047)
passed the exact-source validator and 38-asset integrity checks, then stopped at
one possible-credential finding. The release remains draft until complete
requalification and publication succeed.

The finding came from the Apple Silicon DMG, **656,955,919 bytes**, SHA-256
`b6f9d960c2de4d119e81b50f41450d92c2349bfa5c94682f4788ba79e0d7a5c7`.
Private inspection confirmed the complete, NUL-terminated `hexkey:` C string
containing OpenSSL's published default FIPS integrity constant. Its immutable
upstream provenance and scanner-fragmentation behavior are documented in the
[earlier investigation](2026-10-23-openssl-scan.md). A different buffer boundary
produced a different partial match this time.

The [scanner](../../deploy/secret_scan.py) now recognizes only the **complete
72-byte public C string** before fragmenting input. It substitutes 64 zeroes in
its private scan copy, preserving offsets, newlines and every surrounding byte.
A 71-byte carry handles a match across a one-MiB read boundary. The report counts
these substitutions. Partial values, changed keys and longer custom keys that
share the public prefix remain unchanged; the trailing NUL is mandatory.
The original artifact is never modified.

This correction adds no filename exception, line exception or new prefix
allowlist. The existing rules and all six credential-detection placements
remain active, including credentials next to the public value and its prior
fragment. Native executable internals are not decompiled, and encrypted content
is not decrypted; the scan retains its documented limits.

On **28 October 2026**, all **45 focused scanner tests** and Ruff passed. One
scan of the exact rejected DMG with this correction returned **zero findings**,
**one complete public-literal substitution**, and all six mandatory canaries
passed. The five recorded source and dependency inputs are unchanged.
These results qualify the scanner correction and that exact asset. They do not
replace the full uploaded-inventory, signatures, feeds and publication gates.

The trusted verifier can apply this reviewed correction to the unchanged frozen
release. No native rebuild or telemetry collection enablement is needed. Actual
publication and installed versions remain tracked in
[release status](../RELEASE_STATUS.md).
