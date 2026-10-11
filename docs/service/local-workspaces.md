# Local workspace operation and address recovery

Current source includes a private local engine and guided desktop setup. These
changes are awaiting the complete installed-platform gates; published 4.0.10
connects to an existing service. See [native packaging](../implementation/native-desktop-packaging.md)
and the [app setup requirements](../implementation/app-onboarding.md).

The local workspace belongs to the operating-system account that created it.
Its API listens only on `127.0.0.1`, with a separate private PostgreSQL port.
An ordinary memory API key does not grant permission to administer the host.

## Recover an occupied API port in Studio

If another program occupies the saved local address, startup stops and shows
**Local workspace address** on the local setup screen. Existing memories, keys,
models and RAM settings remain in place.

1. Select **Automatic** for an available port, or enter a specific port between
   1024 and 65535. The private database port cannot be used for the API.
2. Select **Save local address**. An unavailable specific port is rejected;
   Mnemion does not silently substitute another one.
3. Review the saved address, then select **Resume local workspace**. Saving
   does not start the service. Studio reconnects after the normal readiness
   checks succeed.
4. Update locally configured agents that still use the previous API/MCP address.

Pause a running workspace before changing its address. If another local session
changes the settings while you are editing, Studio retains your choice and
requires **Refresh current address** before saving it. Address writes also wait
for other host operations and finish before the app exits or replaces itself.
The OS can allocate a saved port to another program before a later start;
startup checks availability again and offers the same recovery path.

This flow changes the API port only. Database-port recovery, moving the data
folder and guided backup restoration remain separate work. It does not expose
the computer to a network or recover a stopped remote host.

## Equivalent local operator command

An authorized agent running as the workspace's OS account can use the same
operation. The bundled `mnemion-engine` accepts the same `local` subcommands as
`mnemion-service`. Keep the workspace stopped and read its saved identity first:

```sh
mnemion-service local status --root DATA_FOLDER
mnemion-service local port --root DATA_FOLDER
```

The second command reads one JSON line from standard input (maximum 4096 bytes):

```json
{"workspace_id":"00000000-0000-4000-8000-000000000001","expected_port":7892,"port":null}
```

Replace the example UUID and `expected_port` with `settings.workspace_id` and
`settings.port` from the status response. `null` selects an available port;
an integer requests that exact port. Unknown fields, listener hosts, invalid
ports, a stale observed port and a different workspace identity are refused.

The operation holds the same exclusive workspace lock as the running engine,
reserves the chosen loopback address while atomically saving it, and returns a
normal JSON status without credentials. `workspace_busy` means the engine or
another operator still owns the lock. Refresh after an interrupted/unconfirmed
write before retrying; do not edit private configuration files around the lock.

RAM changes and damaged-policy recovery have separate typed commands, described
in [memory resources](memory-resources.md). Host lifecycle, team access and
remote agent operations retain their separate authorization boundaries.
