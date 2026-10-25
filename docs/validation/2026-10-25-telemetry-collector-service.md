# Dedicated collector source validation

**25 October 2026; unreleased source, V08 Building.** This adds a dedicated
TLS entrypoint and a separately locked collector runtime. No public collector
was deployed, no production destination was selected and no product sender was
enabled. The disclosure and release-owned route remain false/null/null.
All 66 requirements remain retained.

## Implemented boundary

The [server](../../mnemion/product_telemetry/server.py) uses Uvicorn/h11 with
TLS 1.3, disabled resumption tickets and key logging, one bounded HTTP exchange
per connection and independent five-second handshake/HTTP deadlines. Requests
are limited to 4 KiB including headers and framing; the existing contribution
body remains exactly four bytes. At most 32 HTTP connections are admitted.

The dedicated protocol does not copy peer/server addresses into its state.
Before aggregation, the metadata boundary clears the original scope and
shared header list, retaining only fixed method/path/query flags. Access,
error, trace and asyncio diagnostic output is discarded in this process.
CLI failures do not echo operator-supplied values. Workspace authentication,
memory APIs and model packages are not loaded.

The existing volatile weekly accumulator and private immutable publisher are
unchanged. Only closed qualifying reports can persist, with eight-week
retention; open-week contributions are discarded on shutdown or restart.
The per-view minimums and uncertainty limits still apply. This is not proof
of useful low-population analytics, authenticated contributors, poisoning
resistance, network anonymity or lifetime privacy.

## Executed checks

| Selection | Result | Scope |
| --- | --- | --- |
| Server, wire and private-publisher selection | **45 passed**, 15.72 s | Existing codec/publisher rules plus actual TLS server requests and shutdown. |
| Server selection using a clean collector interpreter | **7 passed**, 15.24 s | Child servers and report commands ran with only Uvicorn 0.54.0, h11 0.16.0 and Click 8.5.0 installed. |
| Strengthened real-TLS header canary | **1 passed**, 2.20 s | A valid packet carried synthetic authorization, cookie, user-agent, referrer, origin, forwarded-address and request-ID headers. None appeared in responses, logs or the report database. |

The checks also exercise malformed HTTP, overlong headers, incorrect body size,
query/private-path exclusion, stalled handshakes and bodies, TLS 1.2 refusal,
disabled session tickets, an ignored `SSLKEYLOGFILE`, fixed CLI errors and
discarding current-week data on shutdown. The metadata boundary is checked
directly as well. Synthetic canaries contain no user credentials or memory data.
These are separate retained runs, not an invented combined execution.

The [minimal project and lock](../../deploy/collector/pyproject.toml) avoid
installing the full memory engine. CI now repeats its actual server selection
with that clean runtime. The pinned source and test evidence are retained in
the private `2026-10-25-telemetry-collector-service` proof directory.

## Deployment and remaining acceptance

The [operator guide](../implementation/anonymous-product-telemetry-collector.md)
and [Linux service template](../../deploy/collector/mnemion-telemetry.service)
describe a separate non-login account, protected TLS credentials, a private
state directory and configured CPU/memory/socket/logging restrictions. The
template has not been installed; its enforcement, certificate rotation,
capacity and actual host/provider privacy remain unqualified.

Client code and collection policy are unchanged. The existing enabled-client
RSS gap, representative whole-app/renderer and total-wire measurements,
all installed platforms, usable aggregate reporting and production ingress
remain open. This checkpoint is not a public telemetry release or the requested
completion notification. The independently frozen 4.46.8 backup/build repair
continues through its own release pipeline.
