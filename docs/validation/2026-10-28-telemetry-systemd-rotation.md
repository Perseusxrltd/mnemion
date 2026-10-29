# Systemd collector credential rotation — 28 October 2026

An isolated Linux systemd run completed **eight recorded checks** at
**23:55 UTC**, using collector source
`772f5c0bf7f007e2006e35763d659797a4780497` and **440 bound source files**.
It exercised the [credential command](../../deploy/collector/credentials.py)
and repository [service](../../deploy/collector/mnemion-telemetry.service) /
[socket](../../deploy/collector/mnemion-telemetry.socket) templates with
synthetic self-signed certificates A and B. It made no issuer requests.

The fixture retained the existing static service account and shipped sandbox
settings. Its unit substitutions selected isolated source, runtime, state and
credential locations and a loopback-only address/port. Dependencies were
installed offline from the archive's hash-required wheels. This qualifies the
stated systemd credential lifecycle, not the complete telemetry product.

## Retained initial failure

The first fixture prepared certificate A, then recorded
`ConnectionResetError` during its initial request. Its retained systemd journal
reported **`200/CHDIR`**. The fixture applied `umask 077` before
`mkdir(mode=0755)`, leaving the parent directory `0700`; changing descendant
permissions did not make that parent traversable by the service account.
That run remains failed, with its cleanup result and original diagnostic.

The corrected fixture explicitly set its nonsecret parent to `0755` and proved
traversal was denied before that correction and passed afterward. It also
verified a collector-module import under the existing static service account
and removed the first fixture's test-only `DynamicUser=yes` override.
This corrected test setup used the same source/archive, rather than changing
collector code or weakening its credential permissions or sandbox settings.

## Observed lifecycle

| Check | Result |
| --- | --- |
| Parent access and service-account import: two checks | Actual account traversal passed after the parent-mode correction; the collector module imported under that account. |
| Initial A bundle | `changed: true` and `activation: "not_requested"`. |
| Running service with A | Systemd reported an active process. Its presented certificate matched A; one four-byte synthetic report returned HTTP 204 with an empty response body. The listener was loopback-only. |
| Active rotation to B | `changed: true` and `activation: "restarted"`. The actual service PID changed, the presented certificate matched B, and a second four-byte synthetic report returned HTTP 204. |
| Previous trust | A client trusting only A rejected B with `SSLCertVerificationError` before sending another report. |
| Unchanged B | `changed: false` and `activation: "not_requested"`; the service PID stayed unchanged. |
| Stopped collector | After both units stopped, copying A with `--restart-active` returned `activation: "not_running"`. The service stayed inactive and no fixture listener remained. |

After stopping, the one report database contained **zero completed-window
reports**. This checks that particular fixture's report table; it is not an
ingress-log, backup or general retention audit.

Cleanup passed: temporary units, runtime and state were removed. Production
collector units were absent before and after the fixture. The existing memory
service kept the same PID, and the Certbot timer remained active and waiting.
No public listener or production collection was enabled.

## Evidence binding

The original private receipts are retained without publishing operational
paths, account details or certificate material. The successful result's hash
matches its qualification receipt.

| Retained artifact | SHA-256 |
| --- | --- |
| Successful host result | `2474d8d429f493d1ec5aa395e6cc37fe0acb66c8e55f61c33f4baa657e333cc4` |
| Source/runtime archive, shared by both fixtures | `2cfb88765da6fb6a3d0799fa6be7dcb0e46d4abb497e87875d1a8a75e502a5a7` |
| Corrected fixture script | `a4a05198dcd1423c9524c94795a582361374ad6983903fd5431229085c28ef5f` |
| Original failed host result | `c81b00612a2befcf9a9240a5e63f10e4889134b6f781e66263614bf25596cde5` |
| Access/journal preflight | `8d343d4a434b1ced1ca4afa204e43925b5dc109f7fdcd46f04ce5f37addece92` |

## Remaining acceptance

The earlier [certificate preparation result](2026-10-28-telemetry-certificates.md)
and [operator guide](../guides/telemetry-collector-certificates.md) retain their
scopes. This run adds actual systemd activation with synthetic certificates; it
does not establish issuer renewal, the deployed Certbot renewal journey, public
CA trust, public ingress/provider/privacy or installed client delivery.
It also supplies no resource measurement, whole-wire bound or complete workflow
coverage.

V08 remains **Building**. Production collection/destination/route are
**false/null/null**, release CAs are empty, and all budgets and **66 requirement
states** remain unchanged. The [acceptance ledger](2026-10-27-telemetry-acceptance-ledger.md)
retains the remaining privacy, resource, platform and release work.
