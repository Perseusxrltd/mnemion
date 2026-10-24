# 4.46.6 security release and installed update acceptance

Recorded by Codex on 24 October 2026. This closes the qualification of the
[4.46.6 security update](../releases/4.46.6.md), not the separate telemetry
milestone or the remaining roadmap.

The published source is `a5c3bf29e8feb22d73b4047a13ac93df694dcb0c`.
[4.46.6](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.6) was
published at **01:55:55 UTC** after the existing release gates passed.

| Gate | Evidence |
| --- | --- |
| Six native packages and installed journeys | [Release run 40047223740](https://github.com/Perseusxrltd/mnemion/actions/runs/40047223740), successful; 59 required checks per target |
| Artifact verification | [Run 40051560833](https://github.com/Perseusxrltd/mnemion/actions/runs/40051560833), successful |
| Six public upgrade journeys | [Run 40052003118](https://github.com/Perseusxrltd/mnemion/actions/runs/40052003118), successful at 02:07:54 UTC |
| Automatic website release synchronization | [Run 40052000728](https://github.com/Perseusxrltd/mnemion/actions/runs/40052000728), successful |
| Actual Windows and shared-host update | Paired acceptance at 02:15:05 UTC; both observed at 4.46.6 |

Native targets are macOS, Windows and Linux on x64 and ARM64. Windows ARM64
continues to use the documented x64 engine/database compatibility path; a native
ARM64 desktop package is not a claim of a native ARM64 engine.

The actual installed pair updated from 4.46.5. The host used its compatible
automatic updater. Windows used the app's **guarded, agent-requested restart**
after readiness checks; this is not evidence of an unattended idle restart.
No forced installation or restart occurred. A temporary desktop-control
unavailable response during observation remains preserved in the private
diagnostic; later observation and the complete acceptance journey passed.

The existing isolated lab completed **45 requests**, with all three identities
and their exact evidence retained. The personal login, bookmarks and preferences
were preserved. The receipt records **zero production memory writes, zero cloud
model calls and zero pending cleanup**. The earlier custody, backup and restore
journeys were not replayed for this dependency-only update.

The native qualification receipt has SHA-256
`b360ea8e5a1698e30bfab17b4932f767e79c639458dda6cfcfbfad56464dc7fb`.
The actual paired acceptance receipt has SHA-256
`271662275f09d1a0cf6d120b828fc8c9bdabb33d181bf1d03693f74a4066cf46`.
Raw operator files remain private; the public evidence above contains no access
credentials or workspace memory.

Product telemetry source work is not included in this release. Its collection,
delivery, privacy and platform acceptance remain tracked separately in
[V08](../implementation/anonymous-product-telemetry.md).
