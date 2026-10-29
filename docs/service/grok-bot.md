# Connect Grok Bot to Mnemion

By **Perseus XR**. Official route checked **29 October 2026**.

The [official Grok Bot guide](https://docs.x.ai/grok-bot/computer-and-apps.md)
explicitly supports adding an MCP server outside the app catalog by **URL** or
by a **command on the Bot's cloud computer**. A catalog listing is not required
for either route. Mnemion's [Grok Bot package](agent-packages.md) is a connection
card and guide; it is not an importable marketplace plugin.

## Connect by URL

1. In Mnemion, open **Agents & apps**, check the workspace's connection mode and
   copy **Workspace MCP address**, including `/mcp`. Use its configured HTTPS
   address, such as `https://memory.example.com/mcp`.
2. Ask the Bot to add that MCP server. For example: “Add Mnemion from Perseus XR
   at `https://memory.example.com/mcp` using the MCP URL connection.” Replace the
   example address with the intended workspace address; include no credentials.
3. Complete the authentication flow actually offered by the Bot. For a compatible
   OAuth flow, follow [Mnemion account sign-in](hosted-agent-sign-in.md), check the
   workspace and identity, and review the displayed permissions. Use an account
   with the intended grants. If the required authentication option is unavailable,
   retain that limitation for the cloud acceptance check.
4. Send a new message after adding the connection; the provider says the app's
   tools become available from the next message. Discover the available tools,
   call `memory_profile`, then list accessible spaces and fetch a known permitted
   memory. Record the actual result and any authentication or tool error.

**Added** means installed; authentication still needs its own check. Follow the
Bot's **Authenticate**, **Authorize** or reconnect prompt when shown. Use its
secure secret card for a key, or complete sign-in through the browser; keep
passwords and tokens out of chat, URLs and connection descriptions. The provider
requests approval before adding a private-network server or a private CA.

## Connect by a command on the cloud computer

Install the supported Mnemion runtime in that cloud environment and have the
operator provision a [protected application credential file](agents.md) there.
Use a dedicated principal with the required space grants. Register the installed
runtime's absolute path and arguments through the Bot's command-based MCP route:

```sh
/path/to/mnemion-service --credentials /path/to/app.mnemion-credentials.json mcp --transport stdio
```

Both paths are placeholders for files on the **cloud computer**. The credential
file contains the workspace's API origin and application key; it is not part of
the distributable package. The command runs Mnemion's existing stdio adapter,
which connects to the configured service. A Windows or WSL path on your own
computer does not configure the Bot's cloud runtime.

## Shared custody and continuity

The provider documents one cloud computer per account: files, browser sessions
and command-line credentials are shared by its Bots. A command-started MCP
server is also available to the other Bots. Separate names or screens do not
isolate their credentials. Connected-app OAuth tokens instead remain on the
provider's connector backend; do not assume that custody for a command's local
credential file.

Keep durable setup instructions in `/workspace`. Manually installed packages and
virtual environments can disappear after a computer update, recovery or reset;
retain a reinstall procedure and recheck the actual connection afterward. The
workspace's [independent host and recovery route](host-recovery.md) remains
necessary. Observe model quota, cloud-computer availability and endpoint health
separately; this guide makes no claim about an account's current state.

## Acceptance and separate clients

[Issue 44](https://github.com/Perseusxrltd/mnemion/issues/44) remains **open**.
This documents the provider-supported route; actual cloud scoped authentication,
native tool/read/save execution, and restart/persistence acceptance still require
their own evidence. [Conversation capture](capture.md) is configured separately.

Windows **Grok Build**, its `grok-build` profile and `grok plugin install` are
[separate local-client setup](agent-packages.md). Their success, or an ordinary
Grok web connector, does not establish Grok Bot cloud acceptance. Mnemion guides
and distributable packages retain [Perseus XR authorship](../BRANDING.md#connector-and-plugin-authorship).
