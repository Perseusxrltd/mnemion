# Collector IPv6 listener validation — 27 October 2026

The original local `systemd-ipv6` reproduction failed during fixture startup:
the real collector exited **2** with `telemetry_collector_configuration_invalid`
before TLS readiness. Its inherited-listener check accepted only IPv4 and
compared the endpoint with an IPv4 tuple. The original failed log and receipt
remain retained; the receipt SHA-256 is
`9d30547bc6514d55d5a8123eee3358694d33f61c0a4f47c20ad641da4c7291dc`.

The [source correction](../../mnemion/product_telemetry/server.py), based on
`3f8718688f9f8712906d1b88971323e438f041e0`, derives IPv4 or IPv6 from the numeric
configured address. `getaddrinfo` uses `AI_NUMERICHOST | AI_NUMERICSERV` to obtain
the OS socket address, including IPv6 scope fields, without DNS or service-name
lookup. The inherited descriptor must still belong to this PID, be the only
descriptor named `telemetry`, match the family/address/port exactly and be a
listening stream socket. An acquired descriptor is made noninheritable and
closed if socket validation fails.
The change does not select a production address or relax the crash/TLS boundary.

The full [collector test file](../../tests/test_product_telemetry_collector_server.py)
passed **36 tests in 20.95 seconds, with no failures or skips**. Ruff check and
format passed. The selection includes actual IPv4/IPv6 loopback TLS in standalone
and inherited-socket modes, wrong family/address/port and datagram/non-listening
refusals, and an added IPv6 inherited-socket crash case. The latter aborts an owned
serving child with a synthetic incomplete TLS request; the kernel reports
`CLD_KILLED`, not `CLD_DUMPED`. Fixture output, TLS key logs and retained canary
checks remain clean, and a fresh report-export process sees no report.

The verified, unchanged source/test selection contains 435 inputs, digest
`1236cebf962a00092cae5b6b942a0aced1416d4fa7f2f920d2e295aad93f4a73`.
The completed check receipt SHA-256 is
`0f0174681101f3b2176512fcba25504a4a463728d96690482d006620bbe46c14`.
These 36 cases include the earlier
[21-case crash selection](2026-10-27-telemetry-collector-crash.md); the counts are
not additive. Local fixtures hand descriptors to the child rather than installing
systemd units. Nonzero IPv6 scope/interface behavior is not qualified by this
selection. The later [actual host systemd probe](2026-10-27-telemetry-host-crash.md)
qualified IPv6 loopback handoff, one automatic restart after a controlled crash
and eight sandbox checks against 437 deployed source inputs. Its original
controller failed only when a restricted PATH could not resolve the report
inspection executable; separate retained-state inspection passed without another
service start or crash. That original failure remains retained. The local and
actual-host evidence have distinct scopes; neither enables production collection.

The [collector acceptance gates](../implementation/anonymous-product-telemetry-collector.md)
and all 66 requirement states remain unchanged. V08 remains **Building**;
production collection/destination/route stay **false/null/null**, with empty
release authorities. The prior [six actual app journeys](2026-10-27-telemetry-sql-comparison.md)
passed functionally but failed RAM qualification. The 2 MiB / 0.5% ceilings,
resource, installed/platform, actual ingress/provider privacy and full telemetry
acceptance remain open.
