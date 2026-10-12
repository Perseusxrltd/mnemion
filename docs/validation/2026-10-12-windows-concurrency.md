# Actual Windows concurrency check — 2026-10-12

The installed Windows lab completed a bounded, read-only check against the
original shared **4.1.1** service at **12:05:15 UTC**. All **27 requests** passed
in **12.015 seconds**, including **19 semantic search attempts** and a final
successful single-request recovery check. The client reached **10 requests in
flight**. See the [numeric record](2026-10-12-windows-concurrency.json).

| Stage | Parallel requests | p50 | p95 / maximum |
| --- | ---: | ---: | ---: |
| Initial request | 1 | 2,834.11 ms | 2,834.11 ms |
| First burst | 2 | 414.99 ms | 638.84 ms |
| Second burst | 5 | 889.12 ms | 892.73 ms |
| Third burst | 10 | 465.96 ms | 891.73 ms |
| Recovery request | 1 | 385.13 ms | 385.13 ms |

Each request selected the existing isolated contributor space and a fresh,
unmatched synthetic run filter. Successful searches had no hits and retained
the approved generation and space mapping. Eight identity and model-policy
reads checked the contributor, its sole permitted space, and the separately
protected human administrator used only for the policy reads. The approved
generation remained a local CPU model; no cloud profile was approved. The
probe made **no memory or model-policy writes**.

Peak client RSS was **45,830,144 bytes**; minimum observed free Windows RAM was
**872,775,680 bytes**. The harness refuses work below 768 MiB available RAM or
above 128 MiB client RSS. It caps work at 32 requests, 10 in flight, 60 seconds
and 128 KiB per response. A shared private lock prevents overlap with the
existing synthetic write cycle. Credentials stay in the Windows protection
context; reports exclude credentials, endpoints, identifiers and memory content.
Six fixture tests cover refusal bounds, scope guards, timeout/size failures,
retry hints, recovery and report redaction. The new **Run bounded concurrency
check.cmd** launcher is installed in the private Windows lab.

An earlier attempt stopped at **11:57:07 UTC**, after one identity request,
because the tunnel reported its host offline. It sent no semantic requests.
The provider's Computer view showed the remote machine asleep. Using its
existing **Wake** control restored the same authenticated workspace without
sending an agent chat request, replacing credentials or manually restarting
Mnemion. This is independent operator recovery, not unattended availability or
automatic failover; the [host-continuity work](../implementation/workspace-continuity.md)
remains open.

No `inference_busy` response occurred in the live bursts. These network timings
do not establish the server's saturation point, maximum throughput, sustained
capacity, model quality or physical inference concurrency. The deterministic
[4.1.2 overload checks](2026-10-12-busy-fallback.md) separately exercise busy
responses and explicit keyword fallback. The live server in this record was
still 4.1.1; this is not a live acceptance claim for that new fallback.
