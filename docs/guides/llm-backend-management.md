# Manage a legacy LLM backend

These commands manage the classic CLI backend used for legacy contradiction
detection. Studio provider settings are separate. The
[source validation report](../validation/2026-10-27-managed-model-custody.md)
records the current process-control changes and their qualification limits.

Run `mnemion llm setup` to choose a backend, endpoint and model. For `vllm` or
`custom`, the wizard also offers a start script, startup timeout and idle
timeout. Set idle minutes to **0** to disable automatic idle stopping; the
saved `idle_timeout` value uses seconds. Choosing `none` disables this legacy
backend. The setup wizard can contact the configured backend and send a short
test prompt.

| Command | Meaning |
| --- | --- |
| `mnemion llm status` | Display configuration and endpoint reachability. A responding endpoint does not establish process ownership or a successful model reply. |
| `mnemion llm start` | Start the configured managed script and wait for readiness, or report an already-reachable endpoint. A backend without a managed script must be started by its original manager. |
| `mnemion llm test` | Send a real short prompt to the selected backend. It passes only when the trimmed reply is exactly `MNEMION_OK`. |
| `mnemion llm stop` | Attempt verified native shutdown even when the endpoint is unreachable. A manual stop may interrupt active work. |

For scripting, `llm test` returns **0** only for that exact reply, **1** for a
missing, empty or incorrect reply, and **2** when no backend is configured.
`llm start` returns **1** when startup cannot be confirmed and **2** when the
backend is disabled or has no supported managed launch. `llm stop` returns
**2** for absent or unverified custody, including an unreachable endpoint with
no verified record. It returns **1** if the recorded stop is verified but the
endpoint remains reachable. No managed backend is an exit **0** no-op; verified
shutdown with an unreachable endpoint also returns **0**. A private stopped
receipt makes later verified stops idempotent. Reachability alone never proves
that a process ended.

Start scripts must keep the server in the foreground, either by replacing the
script process or waiting for its child. A script that starts a daemon and
exits loses the process relationship needed for later control. Native Unix
scripts run through `bash`; native Windows `.ps1` scripts use PowerShell
`-File`, and `.exe` files launch directly. Script paths are individual
arguments, so spaces do not require inserting shell quoting into the saved
path. These source launch branches do not establish all-platform qualification.
Use an absolute native script path for consistent control from later commands:
custody keys include the resolved arguments, so identical relative names in
different working directories do not share a launch record.

On Windows, `wsl:///home/user/run-model.sh` selects the configured `wsl_distro`
(default `Ubuntu`); `wsl://Debian/home/user/run-model.sh` selects `Debian`
explicitly. Use an absolute guest path and LF line endings. Mnemion passes the
path as one argument and leaves the script unchanged. The native `wsl.exe`
launcher does **not** prove ownership of the guest server: guest stop, restart
and idle teardown are refused. Use the original guest process manager for
those operations. Durable guest process control remains unfinished.

Native control uses a private launch record and verified process identity;
matching an executable name, port or model endpoint is insufficient. An
already-running external server can be used without becoming managed. Keep
the launch record intact. If control is refused because the record is missing,
damaged or unverifiable, use the original process manager instead of deleting
state to force a stop.

Automatic idle stopping and restart defer while recorded Mnemion requests are
active. Old requests and idle watchers cannot control a replacement launch.
Automatic restart holds the stop and relaunch under one private lock, refuses
a still-reachable endpoint and cannot override a recorded explicit stop.
This does not protect unrelated clients that bypass Mnemion's request leases.
Idle checks run while the owning Mnemion watcher is alive; the short
`llm start` command does not install a persistent supervisor.
