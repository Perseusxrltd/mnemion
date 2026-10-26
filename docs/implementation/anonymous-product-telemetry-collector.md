# Dedicated product telemetry collector

**Source implementation, with a 26 October selection follow-up.** The dedicated collector entrypoint
and minimal deployment runtime are implemented. They are not a deployed or
qualified production destination. Product collection remains disabled; the
disclosed destination and release-owned route remain unset. See the
[full V08 contract](anonymous-product-telemetry.md) and
[source validation](../validation/2026-10-25-telemetry-collector-service.md).

The collector runs independently of workspace services. It imports no memory
engine, embedding model, workspace authentication or connector. Its separate
[runtime lock](../../deploy/collector/uv.lock) contains Uvicorn 0.54.0, h11 0.16.0
and Click 8.5.0. Mnemion's reviewed source supplies the collector, packet codec,
private-file checks and aggregate publisher; Python supplies TLS and SQLite.

## Request handling

The [entrypoint](../../mnemion/product_telemetry/server.py) accepts TLS 1.3 and
HTTP/1.1. `POST /v1/report` now accepts four-byte wire v2 automatic randomized
reports or canonical fixed reviewed reports;
`OPTIONS /v1/report` supplies fixed credential-free CORS headers. There is no
workspace API, authentication endpoint, live statistics route or report query.
Legacy wire v1 is refused because it cannot distinguish reviewed from automatic
reports. The endpoint path remains unchanged.
Reviewed packets require coordinate `0` and flags `2`; manual preparation uses
the first permitted view without a category measurement or random draw.

| Boundary | Behavior |
| --- | --- |
| Handshake | Five-second deadline; TLS 1.2, session tickets and key logging are disabled. |
| HTTP connection | One exchange, a five-second connection deadline and a 4 KiB total decrypted request limit, including headers and framing. No keepalive or pipelining. |
| Concurrency | At most 32 admitted HTTP connections; listener backlog 64. The service template also bounds file descriptors and memory, including pre-handshake connections. |
| Metadata | Peer/server addresses are not copied into the HTTP protocol state. The original ASGI scope and header list are cleared before aggregation; only fixed method/path/query flags remain. |
| Diagnostics | Access, error, trace and asyncio exception logging are discarded inside this isolated process. Invalid CLI settings produce a fixed error code without echoing supplied values. |
| Responses | No cookies, request identifiers, reflected origins, server or date headers. Malformed HTTP can receive the parser's fixed error response; it contains no request data. |

The network and TLS stack still handle connection metadata transiently. These
source controls do not prove provider, firewall, proxy, tracing or backup
privacy. Adding an ingress proxy requires its own qualification; the collector
does not trust forwarded headers. The categorical randomization bound described
in the [delivery design](anonymous-product-telemetry-delivery.md) does not cover
arbitrary human selection after review or establish network, participation or
lifetime anonymity.

## Storage and reports

The current weekly accumulator stays in memory. Only validated, immutable
closed-week reports can enter the private SQLite publisher, with at most eight
retained weeks and a 1 MiB database ceiling.

Current **report schema v3** retains the volume range introduced in v2: a closed
week with at least **64 accepted automatic or reviewed reports** can expose
one global power-of-two volume bucket, such
as `[64, 128)`. Below that threshold there is no weekly document. This offers
coarse evidence of received contributions during a small launch; it does not
measure people, devices, adoption or total feature usage. Every detailed view
still requires **4,096 automatic reports of its own**; confidence rules, noise and
rare-cell suppression remain unchanged. A volume-only result can therefore
leave all views `insufficient_reports`. Reviewed packets contribute to no
categorical sum, per-view count or precision calculation; no separate manual
count is published. The earlier [weekly-volume source selection](../validation/2026-10-25-telemetry-weekly-volume.md)
passed **67 tests in 17.87 seconds**, including report compatibility and the
actual TLS minimal runtime; it does not qualify production deployment or
installed collection.

The [selection correction](../validation/2026-10-26-telemetry-review-selection.md)
declares `estimation_population: "automatic_reports_only"` and
`reviewed_report_use: "coarse_global_volume_only"`. Categorical estimates require
correctly marked automatic reports with independent randomization and
packet-independent inclusion; this is not authenticated or representative usage.
The reader accepts immutable aggregate **v1/v2 reports** without rewriting them
or adding a missing global bucket. That compatibility does not accept wire v1.
Four-byte size, client budgets, endpoint selection and eight-week retention
remain unchanged.
The `server reports` command's outer envelope remains `schema_version: 1`;
each report item carries its own schema version, with a root `report_range`
in v2 and v3.
There is no exact count, identifier, live statistics route or filter API. A
coarse contribution threshold is not an anonymity or distinct-person threshold,
and the volume bucket does not extend the packet's categorical privacy bound
to participation.

The final fixed-body source checks are linked above, including real TLS,
unchanged automatic precision and immutable aggregate v1/v2 readers. They do not qualify
production deployment, installed delivery or full V08. Frozen 4.46.14 excludes
this selection correction, and production collection remains false/null/null.

Stopping or restarting the collector discards the open week's accumulated data;
it never flushes raw reports. Certificate rotation that restarts this process
has the same effect. This loss is intentional under the volatile-state design.

Operators can read retained summaries from the reviewed source directory,
using the separate service account and the same interpreter:

```sh
cd /opt/mnemion-telemetry/source
sudo -u mnemion-telemetry /opt/mnemion-telemetry/venv/bin/python \
  -m mnemion.product_telemetry.server reports \
  --state /var/lib/mnemion-telemetry
```

The command prints structured JSON and refuses a missing report store. Run it
with the store owner's permissions; do not loosen the directory permissions
to make it readable. It exposes no raw contribution or filtering interface.

## Deployment template

The [service unit](../../deploy/collector/mnemion-telemetry.service) and
[socket unit](../../deploy/collector/mnemion-telemetry.socket) are reviewable
templates for a separate Linux service. They are not an installer and do not
change an existing memory service or firewall. Their fixed layout is:

- Reviewed source under `/opt/mnemion-telemetry/source`.
- The minimal locked interpreter under `/opt/mnemion-telemetry/venv`.
- Protected certificate material under `/etc/mnemion-telemetry`, supplied to
  the service with `LoadCredential`.
- Owner-only aggregate state under `/var/lib/mnemion-telemetry`.

From the reviewed source directory, install only the collector dependencies
using the repository's pinned uv version:

```sh
UV_PROJECT_ENVIRONMENT=/opt/mnemion-telemetry/venv \
  uv sync --project deploy/collector --locked --no-dev --python python3.12
```

Provision the dedicated non-login account with the included
[sysusers declaration](../../deploy/collector/mnemion-telemetry.sysusers)
and prepare the protected certificate files before starting the service.
Review the listener first: the socket template opens `0.0.0.0:8443`; keep its
`ListenStream` and the service's `--bind`/`--port` values matched. Then install
both units and enable/start the service:

```sh
sudo systemd-sysusers deploy/collector/mnemion-telemetry.sysusers
sudo install -m 0644 deploy/collector/mnemion-telemetry.service \
  deploy/collector/mnemion-telemetry.socket /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mnemion-telemetry.service
```

Enabling and starting the service also starts its required socket; the socket
does not need separate enablement.

PID 1 creates the listener and hands it to `serve --systemd-socket`. The server
requires exactly one named IPv4 TCP listening descriptor for its own PID,
matching the configured address/port. The process itself cannot `connect` or
`bind`: both system calls return `EPERM`, with no port-binding allowlist needed.
The standalone command below continues to create its own loopback listener.

The service uses the separate account and sets 128 MiB memory, no swap, 25% of
one CPU, 128 file descriptors and 16 tasks. It drops capabilities, discards
stdout/stderr and disables core dumps; the private state directory is its
writable persistent area. A finite [loopback-only VPS stage](../validation/2026-10-25-telemetry-collector-service.md#finite-vps-staging)
verified the configured restrictions. Public ingress, provider privacy and
capacity remain unqualified.

To shut the collector down, stop both units so the listener cannot reactivate it:

```sh
sudo systemctl stop mnemion-telemetry.service mnemion-telemetry.socket
```

For an isolated local TLS check, the command below defaults to loopback. Paths
must be absolute, and the caller must protect the certificate's private key:

```sh
python -m mnemion.product_telemetry.server serve \
  --state /absolute/private/collector-state \
  --certificate /absolute/certificate.pem \
  --private-key /absolute/private-key.pem
```

Before a public destination is selected, the actual certificate, address,
ingress, OS/provider logging, retention and resource behavior remain to be
qualified on free existing infrastructure. Nothing in these commands changes
the client disclosure or enables product telemetry. CI separately runs the
actual TLS checks with the three-dependency runtime so that an accidental
dependency on the full memory engine is detected automatically.
