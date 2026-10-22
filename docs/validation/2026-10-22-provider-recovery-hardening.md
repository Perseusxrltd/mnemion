# Provider, recovery and release hardening

Source validation on **22 October 2026** prepares **4.45.1**. The public
[release status](../RELEASE_STATUS.md) records publication and installed-update
gates; the previously accepted [4.45.0 actual deployment](2026-10-22-4450-live-acceptance.md)
remains its own dated evidence. This report does not claim a new installation
has already upgraded.

| Area | Observed source acceptance |
| --- | --- |
| Provider streams, retries and parsing | 49 focused cases passed across provider/scanner/spreadsheet checks. Real direct and environment-proxy HTTP requests stop slow reads and accept the next request. Socket budgets follow the current operation on reused connections; retries, token reads and progress cannot reset the total budget. Exact-size responses, access-loss semantics, Slack token rotation, Drive exports and ordinary encoded spreadsheet content remain covered. |
| Private validation diagnostics | 20 HTTP/connector-entry cases passed, plus the existing authenticated MCP transport check. Sensitive API routes, nested mappings, large invalid property sets and MCP tool arguments preserve useful schema diagnostics without reproducing arbitrary property names or values. Original failing regression receipts are retained. |
| Backup and recovery | Seven focused cases passed, including actual PostgreSQL restore with later deletions, changed access and keys, and Unicode/locale portability. Database tools retain documented libpq, platform, TLS and passfile settings while dropping unrelated secrets; passwords stay out of command arguments and diagnostics. |
| Optional company browser policy | 26 policy/HTTP cases passed. The default header is unchanged. Restricted origins apply to Studio, workspace, help and OAuth-consent entry routes; assets remain available and the private API still requires authentication. Invalid origins stop configuration rather than restoring broad access. |
| Release secret scans | The pinned Gitleaks wrapper passed its real binary and nested-wheel application/vault-key rejection controls and a complete source scan. Normal source integration checks the snapshot before pushing. CI, release preparation, generated desktop content and exact downloaded distributions have required scan steps. Fresh and reused Product-check paths retain the release scan. |

The scanner reads supported archive contents as a bounded byte stream, including
Python wheels and filenames normally excluded by upstream defaults. It inspects
binary content even when that content begins the input stream, so upstream
file-type shortcuts cannot silently skip the remaining distribution. It checks
byte, file-count, depth and time limits, verifies the scanner's archive digest,
and keeps only redacted evidence. A failed control, changed input, scan failure or
exhausted limit cannot produce a passing receipt. It does not decrypt encrypted
content or decompile native executable internals; a successful scan is evidence
for the inspected bytes and rules, not proof that every possible secret is absent.

A rehearsal scanned the published 4.45.0 macOS x64 ZIP and checksum list after
checking the ZIP's published SHA-256. It inspected **640,227,908 bytes** across
**3,141 members**, found no matches, and passed both rejection controls. The
local run took **65.22 seconds** with **82,016 KiB** peak resident memory. This
qualifies the packaged-content path; it does not replace the required scan of
every 4.45.1 distribution. That gate uses a size-based, bounded deadline so the
complete multi-platform release has enough time on a small runner.

Provider deadlines cover socket operations and the accumulated retry/read budget.
Blocking OS name resolution and filesystem operations cannot be preempted by that
socket budget; their elapsed time is checked before further work. The optional
browser policy is an operator setting, not a replacement for authentication,
source permissions or network controls on native desktop connections.

## Native qualification and exit diagnostics

At the **22 October 2026** checkpoint, release run
[39855689596](https://github.com/Perseusxrltd/mnemion/actions/runs/39855689596)
failed installed hosting on [Mac ARM job 120095732920](https://github.com/Perseusxrltd/mnemion/actions/runs/39855689596/job/120095732920)
during `backup-resume`. The local engine reached ready and then stopped while
the parent Electron process remained alive. The exact cause is unknown; the
original receipt and log remain preserved privately. A requested same-job retry
was refused with **HTTP 403** because the entire workflow was still running.
No retry executed.

The source revision adds a bounded numeric process exit code or allowlisted
signal to the existing structured diagnostic. Any original error code, category
and validated code locations are retained. The installed-hosting evidence
revalidates the engine diagnostic before including it in the bounded failure
receipt; raw stderr, exception text and private paths remain outside that record.
An invalid diagnostic is reported as invalid rather than copied into evidence.

The diagnostic revision subsequently passed its **TypeScript build** and
**84 focused component tests**, with **0 failed or skipped**, in **3.515 seconds**.
These cover local workspaces, local backups and the desktop operator. The
installed-hosting script syntax check and `git diff --check` also passed. An
initial build caught a missing imported type; it was corrected before the passing
build and tests, and the original initial log remains preserved privately.

The other five native jobs were **still running** at the recorded failure
checkpoint. These bounded source results do not establish the cause of the
original failure, corrected Mac qualification, publication or actual updates.
The source acceptances above retain their stated scope. Current outcomes come
from [release status](../RELEASE_STATUS.md).

Frozen native builds, signed uploaded artifacts, public installed-update checks,
website synchronization and the next real Windows/shared-host acceptance remain
required through the normal release process. No database migration is introduced.
All **65 requirements** and open GitHub **#44/#45** remain tracked; this batch
does not mark broader provider, fleet, recovery or layered-librarian work complete.
