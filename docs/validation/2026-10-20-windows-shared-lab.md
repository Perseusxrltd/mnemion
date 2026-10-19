# Actual Windows shared-workspace lab

Recorded 20 October 2026 (Europe/Paris), executed 19 October at 23:33–23:38 UTC.
The actual Windows x64 app and independent shared host were both **4.28.0**
after their [ordinary automatic updates](2026-10-20-shared-workspace-adoption.md).
The app retained its protected human administrator login.

## Isolated authority and custody

One dedicated synthetic space and a separate application key were enrolled.
The key has contributor access to that space only, no organization administrator
authority and a 90-day expiry. Actual requests denied organization administration
and all eight pre-existing spaces. Only the human administrator and lab identity
have grants to the new space. Existing agent keys and grants were unchanged.

The prior verified Windows harness was copied into a separate protected folder;
the older office harness and profiles were preserved. Credentials use CurrentUser
DPAPI with a verified protect/unprotect round trip and private Windows files.
The independent administrator credential is used only for the two explicitly
allowed identity/model-policy GET routes. All memory operations use the contributor.

Every cycle checks the exact tenant, application, sole permitted space and pinned
local CPU generation before work. Model-policy changes, pending cleanup, low
available RAM or an expired key stop the run. No cloud model profile is approved.

## Measured checks

| Check | Result |
| --- | --- |
| Write/index/search/revision/cleanup cycle | 42 successful requests in 21.335 seconds |
| Request latency for that cycle | p50 152.36 ms; p95 220.19 ms; maximum 450.44 ms |
| Synthetic notes | Three created, idempotency verified, all indexed and all withdrawn |
| Search and revision | Expected lexical/semantic evidence; saved revision; stale update rejected |
| Cycle process memory | Peak observed client RSS 44,937,216 bytes; minimum observed system free RAM 1,061,937,152 bytes |
| Read-only concurrency | 27 successful requests, 19 semantic attempts, 3.81 seconds |
| Largest wave | Ten requests in flight; p95 594.82 ms |
| Recovery after that wave | Single-request check passed in 178.68 ms |
| Production memory/model-policy writes | Zero |
| Cloud model calls and remaining synthetic cleanup | Zero |

The cycle retains a maximum of 120 requests, two starts per second, one request
in flight, a 120-second work deadline and 45-second cleanup deadline. Responses
are capped at 128 KiB and client RSS at 192 MiB. The separate read-only probe
allows at most 32 requests, ten in flight and 60 seconds, with 128 MiB client RSS.
Both refuse insufficient free RAM and share a private non-overlap lock.

These are measured short checks on one Windows-to-Unix connection. They did not
reach saturation and do not establish server throughput, fleet capacity, minimum
hardware or representative retrieval quality. Client RSS excludes other processes.

## Automatic checks after updates

A user-level Windows scheduled task checks app/server versions hourly and at
sign-in. A new pair triggers one bounded cycle. A verified pair skips the cycle;
a failed attempt for the same versions has a 24-hour cooldown. Unfinished cleanup
blocks new write runs. Concurrency bursts remain manual. Normal battery
restrictions, a six-minute task deadline and single-instance scheduling remain.

The current successful manual cycle seeded the record. The actual scheduled
invocation then returned `already_verified` without rerunning memory work.
Records and launchers are private on the user's PC, with a desktop shortcut and
instructions for disabling the task. No cloud scheduler, subscription or agent
session is involved. This is operator validation of this deployment, not a new
runtime prerequisite for Mnemion or a substitute for native release gates.

Private artifacts retain exact timings and cleanup identities. The public
report excludes host addresses, credentials, account identifiers and memory text.
