# Collector certificate renewal — 28 October 2026

The 4.46.45 [rotation command](../../deploy/collector/credentials.py) and
[operator guide](../guides/telemetry-collector-certificates.md) prepare automatic
renewal for the separate Linux collector. Runtime source is
`046f423bb179745403230c960ba694d73e39daac`; the qualified helper SHA-256 is
`6ce34ac0becf46630091edf3478a04afc1a5b01d98208facd58d2f687546d978`.

The earlier unit loaded two independently copied credential files. The new
unit takes one private `tls.pem` snapshot for both certificate and key.
The helper validates a bounded pair, expected hostname and remaining lifetime
with an in-memory TLS handshake before atomic replacement. It uses no network
connection or issuer API. Unchanged material and unrelated Certbot lineages
do not rewrite the bundle or restart a service.

## Source qualification

All **23 focused tests passed**, with no failures or skips. They cover genuine
matching and mismatched keys, hostname/current-validity failures, near expiry,
input and destination permissions, hard links, symlinks, oversized input,
nonblocking FIFO refusal, competing processes, readers during eight alternating
credential rotations, bounded active-service control and fixed CLI errors.

One test starts the actual collector with the single generated bundle and
receives HTTP 204 over TLS for a synthetic report. Its fixture verifies empty
stdout/stderr, no TLS key log, bounded shutdown and no retained individual
reports. This is a Linux source/runtime fixture, not an installed systemd or
six-platform delivery qualification. Service-control branches use a controlled
systemctl substitute; they do not claim a production restart.

Lint and normal release preparation passed. The **445 recorded source inputs**
remained unchanged after those checks and the initial runtime commit. The
20-file reviewed patch passed secret scanning with zero findings. The client
runtime, production route, collection flag, wire format and resource budgets
are unchanged by this collector provisioning change.

## Existing free-host preparation

At **12:18 UTC**, one bounded preparation on the existing Linux VPS installed
the exact tested helper, a root-owned Certbot deploy hook and a validated bundle
from its existing free certificate. No certificate was issued or renewed.
The host preparation receipt SHA-256 is
`139170ada4c8ce90920f08e8851b6911743c8903bf689552ab4775d911237b12`.

The installed hook was then invoked with that real lineage. It returned
`changed: false` and `activation: "not_requested"`; the bundle's inode, size
and modification time stayed unchanged. The credential directory was `0700`
and its bundle `0600`. Private key material stayed on the host.

The memory-service process and all observed unit states stayed unchanged.
The existing Certbot timer remained active. Both production collector units
were absent before and after, and port 8443 had no listener. No firewall rule
was changed. This verifies credential preparation and hook execution with
unchanged material; future issuer renewal and an actual running collector's
reload still need their deployment acceptance.

The accompanying read-only inspection still found ten IPv4/IPv6 firewall
logging targets. It read no request logs and does not qualify their routing,
provider traffic logging, monitoring or backups.

## Remaining acceptance

Public ingress and release trust remain unset. Production collection stays
disabled, and all 66 requirement states remain unchanged with V08 Building.
The existing RAM failures and **2 MiB / 0.5%** budgets remain in force;
no resource comparison was dispatched or relabeled.

Complete public/provider privacy, whole-wire, actual certificate activation,
installed platform delivery, aggregate utility and resource acceptance before
claiming full telemetry or sending its completion notice. The
[acceptance ledger](2026-10-27-telemetry-acceptance-ledger.md) retains those gates.
