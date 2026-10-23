# Release scan: reviewed public metadata

**23 October 2026 source policy checkpoint.** This records a correction to the
release verifier, not publication of a new product build. Current availability
and release gates remain owned by [release status](../RELEASE_STATUS.md).

## Retained failure and classification

[Release run 39860098559](https://github.com/Perseusxrltd/mnemion/actions/runs/39860098559)
passed all six native gates for immutable source
[`70ec58d8dbf4018ee35a9a57bd0a4677ee45cdf1`](https://github.com/Perseusxrltd/mnemion/commit/70ec58d8dbf4018ee35a9a57bd0a4677ee45cdf1).
The subsequent [artifact verifier 39872601355](https://github.com/Perseusxrltd/mnemion/actions/runs/39872601355)
failed its secret scan. Native qualification did not override that rejection or
authorize publication. The earlier native failures remain in the
[hardening validation history](2026-10-22-provider-recovery-hardening.md#native-qualification-and-exit-diagnostics).

The local artifact-verification receipt at **22 October, 23:46:49 UTC** records
**38 draft-release assets, 4,021,713,596 bytes**, a passing exact-source production
validator and unchanged asset IDs, sizes and digests after verification. The
separate scan receipt at **23:47:17 UTC** records `passed: false`; its existing
archive and binary-first canaries passed. These are distinct outcomes.

All five scan findings were traced to public metadata:

| Findings | Inspected location and classification |
| --- | --- |
| 2 | `cryptography` 50.0.2 macOS x64 wheel, `cryptography/hazmat/bindings/_rust/openssl/hpke.pyi`, lines 77 and 101: the same complete X25519 private-key type annotation, with no key value. |
| 3 | The signed `service-update.json` metadata: SHA-256 values for migrations 013, 016 and 020, each matching the corresponding immutable source file. |

The three reviewed public digests are:

| Migration | SHA-256 |
| --- | --- |
| `013_oauth_bindings.sql` | `9539cddc5ffa9587f192aed9fbe94dd1e92a26ac70233511dbaf86210cee2116` |
| `016_hosted_oauth.sql` | `6ee51bb6929743f5cdc5541a935085f82ec6d95a818db36bbb295a3dd016ae43` |
| `020_secrets_vault.sql` | `71455047ab91b44618a2e0f9a36281fd674df1c8c462f200a058cf267b362963` |

The original bounded receipts, finding locations and digest classification remain
preserved separately. This classification does not rewrite the failed scan as
successful, establish a credential exposure or prove that every possible secret
is absent. Private match data is not reproduced here.

## Policy correction and focused verification

The [scan policy](../../.gitleaks.toml) permits only the complete type-only line
below, with surrounding whitespace including the scanner's line separator, and the three exact
digests above. It does not exempt the whole wheel, manifest, filename or every
64-character value.

```python
private_key: x25519.X25519PrivateKey
```

The [mandatory scanner canary](../../deploy/secret_scan.py) now also requires
rejection of a synthetic application key beside that annotation and another
inside base64-encoded metadata containing a reviewed digest. Existing binary-first,
nested-wheel application-key and vault-key controls remain required. The canary
must observe all required key placements before a scan can pass.

**85 focused regression cases passed in 1.59 seconds.** They cover the bounded
policy exceptions, canary requirements and verifier workflow contract. In
particular, a value or second statement appended to the annotation is not
allowlisted, and unrelated hashes are not accepted by the digest exceptions.
These tests do not replace a complete distribution scan.

The [verification workflow](../../.github/workflows/verify-artifacts.yml) now
checks out its policy at `github.workflow_sha` and runs the distribution scan
from that verifier checkout. Product verification still checks out the exact
completed release source and validates the downloaded assets, signatures and
feeds. The policy correction does not rebuild the frozen product or alter its
uploaded bytes. Publication still depends on successful verification. A failed
job retains available bounded verification/scan receipts separately, without
uploading private credential-match reports.

## Coverage ownership correction

[Main CI 39873108609](https://github.com/Perseusxrltd/mnemion/actions/runs/39873108609)
reported **387 passing legacy tests**, but only **41.29% coverage** because the
new `mnemion/host_control` package was counted in the legacy denominator while
its tests belonged to the service suite. The source correction places that
package in [service coverage](../../deploy/service.coveragerc) and excludes it
from the [legacy denominator](../../deploy/legacy.coveragerc). The service gate
still requires **at least 75%**; no threshold was lowered. Passing legacy tests
alone did not satisfy the failed coverage gate.

## Remaining acceptance

The initial policy correction removed the three checksum findings but still
rejected both annotations: Gitleaks retains a line separator in the value it
checks against line exceptions. A direct pinned-scanner reproduction confirmed
that accepting surrounding whitespace fixes this case while retaining the
whole-line anchor. That rejected full scan is preserved separately. Test
fixtures construct the annotation at runtime, so quoted source statements do
not need broader exemptions.

At this checkpoint corrected GitHub artifact verification and publication had
not completed. CI must also pass with the
corrected coverage ownership. Public installed-update checks, website
reconciliation and actual deployment acceptance retain their separate gates;
this report claims none of those outcomes.

The scanner retains bounded ZIP/wheel/tar.gz/tgz expansion, flattened-byte
inspection and decoding limits. It does not decompile native executable
internals or decrypt encrypted content. A future passing receipt applies only
to its recorded inputs, rules and inspection scope. Original failed receipts
remain historical evidence alongside any later result.
