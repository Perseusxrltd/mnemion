# Actual ChatGPT OAuth acceptance — 20 October 2026

The signed-in ChatGPT web client completed the acceptance requested by
[issue 18](https://github.com/Perseusxrltd/mnemion/issues/18), using Chrome on
Windows and a running Mnemion **4.33.0** shared service. This is an actual client
connection, in addition to the earlier [public protocol exercise](2026-10-20-live-hosted-signin.md).

## Observed result

1. **Plugins → Add → Add custom MCP server** accepted the public HTTPS `/mcp`
   endpoint with **OAuth**, without a pasted bearer token or client secret.
2. ChatGPT's connection notice led to Mnemion's personal sign-in page. Mnemion
   displayed the requesting app and `chatgpt.com` return address.
3. The existing personal account signed in successfully. The consent page
   displayed its organization-administrator authority and actual space roles.
   Explicit **Allow connection** returned to ChatGPT.
4. The resulting private plugin was installed. ChatGPT discovered **16 tools**,
   displayed as **11 read** and **5 write** tools, including `memory_profile`,
   `fetch`, `memory_context`, `memory_fetch` and `memory_map`.
5. **Try in chat** attached the plugin to a new conversation. One requested
   `memory_profile` call completed with an authenticated-success response.
   The exercise requested no memory content or memory mutation.

The existing account's administrator authority was visible and retained. This
was not a restricted-account test. The earlier separate protocol exercise used
a nonadministrator reader and verified denied writes/admin operations, refresh
rotation, revocation and temporary-principal cleanup. Those results keep their
original date and runtime; they are not presented as fresh ChatGPT requests.

## Limits and retained evidence

The model called the principal display name the workspace name in its short
summary. The profile contract uses `name` for the principal and `nickname` for
the workspace. Authentication and tool discovery passed; the response is not
evidence of correct workspace-label interpretation or retrieval quality.

Private consent, discovered-tool and response observations, with SHA-256 hashes,
are retained in the operator's dated acceptance receipt. Credentials, private
workspace identifiers, account details and exported connection packages remain
outside the public repository.

This completes the named ChatGPT connection acceptance. It does not publish a
plugin to the public directory, validate Dot or every OpenAI surface, capture
ChatGPT conversation history, or complete the broader C05/A08/F08 requirements.
Distributable integrations must use [Perseus XR publisher metadata](../BRANDING.md#connector-and-plugin-authorship).

The provider-generated private package was exported, given Perseus XR
`author.name` and `interface.developerName`, the product website and canonical
icon, then reimported through **Upload new version**. ChatGPT displayed version
**1.0.1** and its new category, capabilities and website, but still attributed
the private listing to the creating personal account. Package metadata alone
did not change this provider-controlled display. The package and its private
app reference were retained locally; no public listing was submitted.

Mnemion **4.37.0** was already public for all six native targets when this check
ran; its source includes the exercised OAuth implementation. The
[automatic release record](../RELEASE_STATUS.md) independently tracks native
installation, uploaded artifacts, website synchronization and public updates.
The private shared host's subsequent guarded schema upgrade is a separate
operation and is not implied by this client acceptance.
