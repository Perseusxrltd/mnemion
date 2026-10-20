# Native connector setup and Perseus XR packages — 20 October 2026

The 4.38 source adds Hermes and OpenClaw profiles to the existing app/agent
installer and a shared provider-package generator for the app, API, SDKs and
standalone engine CLI. It preserves existing Grok Build, Claude and Codex setup.

## Measured source acceptance

- **31 focused cases passed** across the existing agent installer, new native
  profile fixtures and real PostgreSQL/HTTP desktop installation. Install,
  observed status, reopen/removal, exact private backups and application/tenant
  checks retained unrelated settings and credentials.
- **37 further focused cases passed** for package generation, extended profile
  paths, authenticated capability/export APIs and organization isolation.
  Packages are deterministic, bounded and free of generated credentials; unsafe
  addresses, duplicate settings and unauthorized or wrong-tenant requests fail.
  The two runs overlap in profile tests and are not reported as 68 distinct cases.
- Actual Windows **Grok Build 1.0.62** accepted its generated plugin manifest and
  discovered its declared MCP component using `grok plugin validate`.
- Actual Windows **Claude Code 2.1.59** first rejected the newer `icon` field.
  The compatible package omits that manifest field while retaining the canonical
  PNG and rendered guide. Native `claude plugin validate` then passed. The first
  failed package remains separate private evidence.
- The branding verifier confirms the package image is byte-identical to the
  canonical app/site mark. Neither validator started a model turn or changed the
  user's installed agent configuration.

- Actual Electron downloads passed through the authenticated API and disposable
  PostgreSQL for Claude, Hermes, OpenClaw and the accurately labeled Grok Bot guide.
  Downloaded ZIP contents retained the configured address and author without
  the session key. Desktop and 500-pixel layouts were inspected; no horizontal
  overflow or console errors occurred. This pre-version-bump source check used
  the 4.37 package label; it does not attribute the new capability to release 4.37.
- The TypeScript SDK, frontend and Electron builds passed. Native delivery probes
  now verify the included package logo/generator and the two new configuration
  formats on each release target. Their built-artifact results remain separate.

The [release status](../RELEASE_STATUS.md) separately records native installers,
uploaded artifacts, website delivery and automatic-update checks. Source tests
and a provider's static manifest validator do not claim a live connection or
public directory approval. The actual desktop download result above is separate from provider login,
model execution and marketplace approval.

## Provider contracts reviewed

Official documentation was fetched on 20 October:

- [OpenAI portable plugins](https://developers.openai.com/plugins/build/plugins).
- [Claude plugin reference](https://code.claude.com/docs/en/plugins-reference).
- [Grok Build plugins](https://docs.x.ai/build/features/skills-plugins-marketplaces)
  and [MCP settings](https://docs.x.ai/build/features/mcp-servers).
- [Hermes MCP configuration](https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp).
- [OpenClaw MCP](https://docs.openclaw.ai/cli/mcp),
  [transport/OAuth source](https://github.com/openclaw/openclaw/blob/main/docs/cli/mcp/transports.md)
  and [native profile path rules](https://github.com/openclaw/openclaw/blob/main/src/cli/profile-utils.ts).
- [Grok Bot computer/app boundaries](https://docs.x.ai/grok-bot/computer-and-apps)
  and [Grok custom MCP reachability](https://docs.x.ai/grok/connectors/custom-mcp-tunneling).

The Bot cloud route is distinct from Grok Build and ordinary Grok web
connectors. [Issue 44](https://github.com/Perseusxrltd/mnemion/issues/44) retains
actual cloud authorization, tool/save/read and restart acceptance. Its observed
quota and computer-availability limitations remain visible. The shared host's
guarded update, original failed lab and paused upstream note publisher are
tracked separately in [issue 45](https://github.com/Perseusxrltd/mnemion/issues/45).

C04/C05/C07/F08 advance without completing their broader provider, capture,
enterprise and provisioning scope. C06 is not completed by exporting a guide.
