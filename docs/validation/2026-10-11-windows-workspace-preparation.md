# Windows workspace recovery and bounded diagnostic preparation

Recorded **2026-10-11** on the user's actual Windows installation. This is
private operational preparation, not evidence of a live remote load test.

- Preserved the available private Markdown source snapshot and Git history in
  an owner-only recovery folder. Source material is not a database backup and
  does not restore unexported writes, identities, grants or the recovery ledger.
- Protected the supplied connection using the installed Windows client's
  current-user DPAPI helper. Verified encryption/decryption without writing a
  plaintext key or inserting an unverified bookmark into the app.
- Installed one-click health/access/MCP checks and an optional bounded read-only
  lexical baseline using existing Python dependencies. No paid account, trial,
  model download, memory mutation or PowerShell policy change was needed.
- Default load limits are 40 requests, 2 per second, 4 concurrent requests and
  45 seconds. Hard limits cap requests, rate, concurrency, duration, response
  size and client memory. The client stops on authentication, network, redirect,
  rate-limit, server-pressure and resource errors. Reports omit credentials,
  private destinations, identity names and memory contents.
- Five fixture checks passed: read-only calls and redacted reports, immediate
  stop on refusal/redirect/offline/rate limits, low-RAM refusal, total deadline
  for slow responses, and response-size bounds.
- The actual Windows preflight returned **tunnel_offline**. Dependent identity,
  scope and MCP checks were skipped and **no load started**. The last known
  application credential does not have organization-administrator authority.

The installed app remained minimized with automatic updates, background mode
and login startup enabled after its earlier observed unmodified 4.0.9 → 4.0.10
update. No local service/model was started to work around the missing host.

Still required: independently authorized host access or a verified recovery
target, a live connection to the intended workspace, a dedicated scope for write
and recovery drills, and end-to-end load/update observations. The private checks
measure client latency and bounded throughput; they do not establish retrieval
quality or the server's maximum capacity.

## Connected follow-up

The host was subsequently woken through its provider operator controls, without
using the unavailable agent. The [4.0.12 release](2026-10-11-v412-release.md)
fixed the native gateway/cache failures. The [connected administration and lab
report](2026-10-12-workspace-administration.md) records the actual app join and
reopen, individual human key, explicit Git reader mapping, scoped test identity
and successful synthetic save/index/search/revision/delete cycle. This earlier
offline preparation is retained as the original observation; verified complete
backups and independent hosting are still required.
