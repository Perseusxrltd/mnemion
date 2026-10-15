# Private desktop control from local agents

The 4.6.0 source adds 19 discoverable actions through the owning OS account's
private desktop pipe. This complements the memory API and MCP. It does not
grant remote memory clients authority over the host computer. The
[operator guide](../service/desktop-operator.md) documents commands, authority,
private key output, identity confirmation, cancellation and bounded retries.

## Focused evidence

- The complete desktop regression passed **154 tests**, including eight new
  transport/client checks. These exercise the actual Python client and Node
  server over a local OS socket, authentication/session refusal, size limits,
  request replay, duplicate in-flight prevention, cancellation, protected key
  output, error redaction, endpoint ownership and action/input discovery.
- **Seven Python checks** cover pipe-address validation on three OS families,
  live/dead process publication, partial-response timeout and response identity.
  These address protocol behavior; platform branches simulated on Linux do not
  count as native Windows or macOS execution.
- TypeScript builds and the complete desktop frontend build passed. The new
  setup panel uses the existing design system and copies executable/argument
  instructions without a credential or pipe address.

## Real desktop and engine walkthrough

A disposable Linux source Electron app used its actual preload, controllers,
owner-only discovery writer, OS socket and CLI. The local engine used bundled
PostgreSQL 18 with TLS/pgvector and a real BGE Small CPU profile. The source
walkthrough ran with the 4.5.0 development version before 4.6.0 preparation.

The agent paused and resumed a protected backup schedule, and the app displayed
the changed policy. Retrying the same request did not change the revision twice;
stale revisions and wrong workspace identities were refused. The CLI captured
a current ledger, authenticated snapshot and ledger files, and created a verified
independent recovery copy with rotated keys and external connections requiring
review. The original workspace remained selected until explicitly changed.

A separate agent-driven roundtrip discovered a verified copy, selected it,
reconnected the app, and returned to the original workspace. An unsaved draft
blocked selection without changing the host. This walkthrough exposed and fixed
a real issue where an agent's backend selection left the renderer on the old
connection: an explicit local selection event now suspends the view during the
handoff and reconnects it afterward without a spurious expired-session message.
Final shutdown returned success and no fixture database PID files remained.

The Linux fixture used an authenticated test cipher because this environment has
no unlocked desktop credential store. It also used the development Chromium
sandbox override. It does **not** establish Linux Secret Service, Windows DPAPI,
macOS Keychain or installed-package acceptance. The installed six-target pipeline
adds the actual bundled CLI, protected endpoint, schedule/restore/selection and
unsaved-draft checks to its existing recovery phases. Those gates must pass
before publication; current availability is in [release status](../RELEASE_STATUS.md).

No production memory, Windows installation, shared host or external provider was
changed by these fixtures. Company host delegation, independently reachable
recovery, fencing/failover, cloud delivery verification, retention and complete
provider workflows remain open under the broader product requirements.
