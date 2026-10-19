# Actual shared-host adoption and personal access

Recorded 20 October 2026 (Europe/Paris); operations ran on 19 October UTC.
This report omits private addresses, account identifiers, credentials and memory
contents. It covers the existing shared-agent workspace, not restoration of the
unavailable original office database or vault.

## Human browser and Windows access

The existing independently authenticated human administrator acquired a personal
password without changing its identity, eight space grants or independent owner
key. Native HTTPS login passed, and the temporary device session was revoked.
The credential has private Linux custody and a verified owner-only Windows
CurrentUser DPAPI copy; it is absent from source, notes and agent configuration.

A fresh Chromium browser then signed in through the actual public web page.
The workspace navigation, people administration, account/session controls and
all eight accessible spaces were present. Remembered login was left off.
Sign-out returned HTTP 200, removed authenticated navigation and returned to the
login form. The temporary browser was closed. This is Mnemion web-app acceptance;
it does not replace the outstanding signed-in ChatGPT OAuth flow.

The user's actual installed Windows x64 app completed its ordinary **4.20 →
4.27** automatic update and relaunch after one normal check request. No manual
installer or forced app restart replaced the updater. The application reported
4.27, with automatic updates, background operation and startup still enabled.
The same app then completed the ordinary **4.27 → 4.28** update and relaunch
after one normal check request. At **23:24 UTC**, the new private desktop
controls selected the existing human account on the actual shared host, also
running 4.28. The authenticated account was an administrator, the password
session was remembered with Windows protection, and the previous bookmark and
all three startup/update/background preferences were retained. No production
memory was written. This establishes actual device setup, not saturation testing.

## Managed host adoption and migration

The existing Unix host ran 4.17 under Supervisor with two external Git source
services. Preparation created a separate managed state using the same database
roles, private application configuration, OAuth origin and source identities.
The signed 4.27 candidate was staged before the maintenance interval. A fresh
off-host full snapshot and later access ledger had already been verified.

At **22:51–22:52 UTC**, a guarded adoption stopped the previous lifecycle,
registered both source runners with the new Supervisor and reopened the same
4.17 workspace. Previous state and exact configuration copies were retained.
The obsolete external source units were disabled, avoiding duplicate runners.

At **22:56–22:58 UTC**, the official migration upgrade created and verified its
encrypted pre-update archive, applied the four appended migrations and activated
4.27. It did not replace or restore the live database. The stable bootstrap
remains separate from the publisher-verified active runtime. No unfinished
upgrade journal remained after success.

Actual external acceptance made **15 read-only HTTP/MCP requests before and 15
after**. Existing owner, Codex and Grok credentials retained their identities,
roles and space grants. Two recorded memories kept their exact versions and
content hashes; an already-deleted memory remained unavailable. MCP discovery,
public OAuth metadata and the human account state were retained. These checks
made no memory writes. Both registered Git sources subsequently completed scans
using the 4.27 launcher and runtime.

## Automatic maintenance and off-host recovery

Automatic compatible service updates were enabled after acceptance. The host's
watchdog now recognizes active managed-update journals so it does not interrupt
an intentional update restart. Backup capture resolves and verifies the active
runtime and includes the two registered source configurations. Desktop updates
and server updates remain separate mechanisms.

The ordinary updater then installed **4.27 → 4.28** automatically. Only its
process was restarted to bring forward the normal startup check; no manual apply,
substitute feed or unverified package was used. Supervisor reported ready with
initialized children and no unfinished recovery. Fifteen additional actual
HTTP/MCP checks retained all three identities and grants, exact memories,
deletion, personal login and OAuth discovery without memory writes.

A new **4.27 full host snapshot** and later **4.27 access/deletion ledger** were
delivered through the existing encrypted private Git mirror at **23:16 UTC**.
An independent authenticated GitHub read at **23:18 UTC** verified the exact
manifest commit, artifact lengths, ciphertext hashes and part totals against the
delivery receipt. This snapshot follows adoption, migration and update enablement.
Private evidence remains with the operator; no recovery key is in Git.

This verifies one real supervised Unix deployment. It does not prove fleet
rollouts, Windows/Compose service adoption, an actual boot cycle, OS/TLS/provider
provisioning, high availability or complete custody of external SSH configuration.
The [managed-update guide](../service/managed-updates.md) and
[host recovery contract](../service/host-recovery.md) retain those boundaries.
