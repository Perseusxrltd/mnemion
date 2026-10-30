# Compiled Linux v3 app review — 30 October 2026

**V08 remains Building.** Collection, destination and route remain false/null/null.
No fleet statistics can be pulled. This note records one original compiled-app
review on source `e36b51a72ca16ec0692d427bbeee912e098d21ef`.

## Original run

GitHub Actions run
[40981256191](https://github.com/Perseusxrltd/mnemion/actions/runs/40981256191)
succeeded on that source. The existing review flow used the real compiled Linux
source app: Electron 44.9.3, Node 24.22.0, x64, packaged false. The journey used
the compiled frontend and the shared app policy and client modules.
Bridge IPC was available with Node integration off. The app run was not repeated
for the reader correction below.

All 10 review controls passed:

- disclosure was required
- setup disclosure was deferred and granted no permission
- the manual choice was made before permission
- the app disclosure was acknowledged
- exact review was preserved
- the native-helper opt-out invalidated the held report
- re-enable started empty
- discard left the attempt unspent
- the approved attempt used the inspected body
- opt-out and manual review mode were still in effect after restart

Two launches. Three save/fetch/recall cycles: 9 memory operations and 12/12
successful API requests, including discovery. Page errors were none. Model
calls were zero.

One user-inspected 25-byte v3 packet was received on the fixture TLS path
`/v3/report`. The collector accepted that one body and recorded no forbidden
metadata. The received body matched the inspected bytes. Wire version was 3.

One 65,536-byte attempt was spent. The lease was cleared. Queue cells were 0.
The database was 28,672 bytes. The maximum producer count was 0. After restart
the opted-out profile had no snapshots, accepted writes, or reserved attempts.
Fixture content was absent from the queue.

Cleanup removed the isolated profiles, stopped the collector, and removed the
certificate profile. The production disclosure was unchanged. 2,311 source
inputs matched.

## Reader correction

The first private reader rejected this original because it required
`comparison: false` inside `source.json`. The workflow writes `comparison` only
when it is true. The actual review metadata is three fields: `source`,
`attribution` false, and `review_journey` true.

The reader was corrected to that schema. The same original artifact qualified.
There was no app rerun. The corrected reader rejected nine negative cases
(source identity, review boolean, wrong mode, wire route, native opt-out,
exact report, spent budget, restart sends, and cleanup) and accepted the
unchanged original.

Original archive SHA-256:
`ca25c4383f309db7152b242bad4c7c35d40c8e317c075f2d33e070ce345ff6a1`.

## Scope

Compiled Linux source app, fixture TLS delivery of the inspected packet, and
restart persistence. `resource_acceptance` remains false. Production collection
was not activated. Installed report delivery, resource gates, whole-wire
measurement, and hosting or provider acceptance stay open. The 2 MiB and 0.5%
ceilings are unchanged.
