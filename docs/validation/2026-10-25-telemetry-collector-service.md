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

## Socket handoff and local checks

The later [server change](../../mnemion/product_telemetry/server.py) adds
`--systemd-socket`: it validates one named IPv4 TCP listening descriptor, its
activation PID and configured address/port. The
[socket unit](../../deploy/collector/mnemion-telemetry.socket) supplies that
listener; the [service](../../deploy/collector/mnemion-telemetry.service) requires
the socket and denies both `connect` and `bind` with `EPERM`. Standalone local
listening remains unchanged. The focused minimal-runtime socket selection
passed **11 tests in 15.77 seconds**; earlier selections above retain their
original source scope.

## Finite VPS staging

Two earlier finite stages failed and remain preserved. At **22:25 UTC**, a denied
connect killed the prestart probe with `SIGSYS`. Returning `EPERM` allowed the
second probe to continue at **22:27 UTC**, but an additional-port bind succeeded:
`SocketBindAllow` was not enforced on that host. Other sandbox checks passed;
the second stage still failed. The final source uses the inherited listener
and denies all process-level binds, without relying on that allowlist.

The third loopback-only stage **passed from 22:33:20.140697 to 22:33:39.845395 UTC**
on 25 October. It used base source
`c3ea02adeb0db666cf2617f76a003b391e7042d2` plus the three hashed socket changes
below. It changed no canonical memory service, backup, public listener or product
collection policy.

| Observed boundary | Result |
| --- | --- |
| Sandbox | All six checks passed: outbound connect denied, additional-port bind denied, unprivileged account, no new privileges, empty capabilities and active seccomp. |
| TLS/HTTP | One accepted report, one rejected path and one malformed request; no reflected canary or session ticket. |
| Actual cgroup settings | 128 MiB maximum, zero swap, CPU quota `25000/100000`, and 16 tasks. |
| Private state and runtime | Directory `0700`, database `0600`; exactly Uvicorn 0.54.0, h11 0.16.0 and Click 8.5.0. |
| Logs and shutdown | Five lifecycle journal records, zero stdout records and no canary. No closed reports after stop; service/socket both inactive/dead, main PID zero, and loopback port 18443 could be rebound. |

Observed peak memory was **22,618,112 bytes** during this short synthetic
collector run. It is not client-resource or collector-capacity qualification.
The finite installed-unit check demonstrates the tested host's enforcement;
it does not qualify a production endpoint, certificate rotation or provider
logging/retention.

| Original evidence/source | SHA-256 |
| --- | --- |
| Local socket-activation checks | `60fbdb4411ffbb61176e9f8241c5f608b02300bd76c5b38fa2efebabcc770a00` |
| First prestart failure receipt | `c98996823a7b29daf7d2bccfc3007712b5ef7809551489f6d718af9acfe99b81` |
| Second bind-restriction failure receipt | `551aea3a2b0123ce80d4493b205d2208fd1bc4238430ca6122260d4ea9b9a637` |
| Third-stage qualification receipt | `7cdca6ee45e2ba8f112866039fe84fbfe7f29d11c71a44c1246e69a8bc29f678` |
| Server socket handoff | `5caf7ff685d42b75bc180edbd5d197b08072c1159ee4fe36e2f4acd09ff954c6` |
| Service unit | `e7b3e6918e1a92f43fc607ab60307a361024060ae3e4f340c4647761ffbe15f4` |
| Socket unit | `2d8b6a420fbfcfe786883910ef8efc090d40432f47123f23863337d004449f08` |

## Deployment and remaining acceptance

The [operator guide](../implementation/anonymous-product-telemetry-collector.md)
describes installing both Linux units, starting/enabling the service that
requires its socket, and stopping both for shutdown. The production template's
listener remains separate from the finite loopback stage. Production deployment,
certificate rotation, capacity and host/provider privacy remain unqualified.

Client code and collection policy are unchanged. The existing enabled-client
RSS gap, representative whole-app/renderer and total-wire measurements,
all installed platforms, usable aggregate reporting and production ingress
remain open. This checkpoint is not a public telemetry release. The independently
frozen 4.46.8 backup/build repair excludes these collector additions; its release
qualification is separate.
