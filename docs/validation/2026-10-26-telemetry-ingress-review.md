# Telemetry ingress and retention review — 26 October 2026

Read-only deployment observations at source checkpoint `39ed946a` confirm that
the production collector and its listener are not installed. This review does
not select a destination, route or release trust, or enable collection.

## Deployment and candidate trust

The collector service/socket units were absent, as were its deployment and state
paths. An existing free Let's Encrypt certificate and active renewal timer offer
a candidate capability, not a deployed telemetry endpoint.

Official ISRG Root X1 (**1,939 PEM bytes**) and X2 (**790 bytes**) fit the existing
one/two-CA bounds. Exactly one TLS 1.3 handshake with HTTP/1.1 ALPN to the existing
memory HTTPS listener used only those two authorities, verified the hostname and
matched the leaf fingerprint observed on the host. It sent no HTTP request or
telemetry report and read no private key. This establishes a feasible free trust
candidate for that listener; collector deployment, certificate rotation,
whole-wire cost and provider privacy remain unqualified.

## Logging, retention and provider limits

The first firewall inventory missed compatibility `xt LOG` targets. The corrected
read found **ten logging targets: five IPv4 and five IPv6**. That correction
supersedes the initial zero-log-target interpretation; both receipts are retained.
UFW selects a log file with **weekly rotation and four retained rotations**, and
a persistent journal directory is present. Those settings do not establish a
qualified privacy path or a complete deletion/retention bound. No network-log
contents were read, and this inventory does not establish which future collector
requests would enter those logs.

Hostinger's [public privacy policy](https://www.hostinger.com/legal/privacy-policy)
describes log data collected through use of the Hostinger Platform. That language
does not establish logging of traffic to this VPS's future collector. The
[DPA](https://www.hostinger.com/legal/dpa) provides contractual terms and assigns
configuration responsibilities; it does not verify this VPS's network logging,
snapshot settings or retention. Provider account settings remain unverified.

Existing backup metadata was observed without reading backup contents or starting
a capture, retry or publication. It does not qualify provider snapshots, backup
retention or exclusions for future telemetry data.

## Separate memory-service health

Both public health endpoints returned HTTP 200 and reported **4.46.22**, with
alive/ready status. These observations establish the responding version only:
authenticated source/client acceptance and the actual automatic-update mechanism
were not established. They do not qualify a telemetry collector.

## Retained evidence and unfinished acceptance

The closed private receipts are identified below without host names, addresses,
account identifiers, configuration contents or private operational artifacts.

| Evidence description | Receipt SHA-256 |
| --- | --- |
| Initial deployment inventory | `c464470558db83d63d4d33b49ceadf5bbf27c1055d25d78acf59148efeddcb34` |
| Corrected listener/firewall/certificate inventory | `720da24972d513f473fcbdf26131dd05a912150271dc024a2b7d7e8fa25a67e9` |
| Retention and renewal metadata | `f54531d0fa4e21dd6c5abc1129b65310083ae64f8d1e8f04449dffbdf6fbcf68` |
| Public provider privacy-policy receipt | `110d4c3b077b7e7d40d2426fcd48e93be5a31f5236d5b41f7cbc549dc0dbd2e5` |
| Public provider DPA receipt | `590cd4f407f02ed411f8bbce34b6ecc3812bb997c83efc517106af61571f5715` |
| Backup metadata observation | `9dabdef773561ba30f9c9ebcc1d24854eea402233a4bb03ed195a021c523c75b` |
| Public health observation | `ccac353657364039f2ab5d9b7e09e5daf49a4689d4c4411f14ce4c76c7a065c3` |
| Bounded candidate-trust handshake | `8b407022408ad38f31abb603f8e605baf89f46c5881e30d7381b3f9c999a3c99` |

The recorded review made no host changes and read no credentials, private keys,
network-log or backup contents. No production collector was launched. The
[RSS failure](2026-10-26-telemetry-scoped-trust-results.md) and
[final browser-pressure refusal](2026-10-26-telemetry-browser-pressure.md) remain
open, with the 2 MiB / 0.5% budgets unchanged. Provider/backup privacy,
installed-platform and full V08 acceptance remain open. All 66 requirement states
are unchanged; V08 stays Building with collection/destination/route
false/null/null and an empty release authority list.
