# Live conversation and desktop shutdown validation — 19 October 2026

The 4.17.0 batch adds a separate bounded JSONL source adapter and a desktop
control-process drain. All capture inputs are synthetic files; service checks
use isolated PostgreSQL and real HTTP with separate identities. No personal
history, running office workspace or user installation was modified.

**55 focused Python checks passed:** 27 new live-file cases, 20 existing provider
checks, seven new service/HTTP cases and the existing competing-runner regression.
They establish:

- Half records and split UTF-8 tails wait, then produce the same fragment identity
  when completed. Replacing only unfinished text preserves the captured generation.
- Raw fragments preserve text and byte/line ranges above the ordinary selected-file
  limit; individual record, file, fragment and deadline limits remain explicit.
- Unchanged files reuse exact references with zero content reads. Appends reprocess
  the final fragment and new records while hashing the sealed prefix. Reprocessed
  fragments with unchanged revisions also reuse references. A simultaneous edit
  to older bytes is detected; append-only growth is never assumed from size alone.
- Appends during scanning use a frozen boundary and continue on the next scan.
  Conflicting in-flight edits fail without acknowledging the local checkpoint.
- Lost acknowledgments and mismatched service cursors trigger evidence replay.
  A real HTTP response deliberately lost after server commit produced unchanged
  observations on retry, with no duplicate memories.
- Codex header identity persists across fragments; explicit ACP event identities
  deduplicate across sealed fragments and repeated scans while raw events remain.
  Unknown JSON and raw-only capture do not invent conversation turns.
- Invalid complete JSON, private Mnemion controls, journal records, unverified
  links and mismatched checkpoint ownership are refused. Source body text and
  credentials do not enter the private checkpoint database.
- A bad/oversized file suspends its own scope while an unrelated valid file remains
  readable. Removing a user mapping still denies that user after cached references
  and fresh source checks. Disappearing files close their source access.
- Truncation starts a new generation: a real service test appended seven new turns
  after shortening a five-turn file and retained every new raw/readable fragment.
- References cannot create a missing source revision or change it. Corrections,
  proposals, quarantine and forgetting survive reference-only snapshots.
- The service commits capture counters only after a complete inventory, and the
  runner refuses a pre-4.17 server before creating capture state.

**16 TypeScript client checks passed**, including bounded checkpoint parsing,
older/missing checkpoint compatibility and the 4.17 feature gate. Both web and
Electron renderers, the TypeScript library and desktop process compiler build
successfully. Native installation and delivery remain part of the release pipeline.

**49 desktop controller checks passed.** A new test first reproduced premature
quit completion while an independent vault-control process remained open. The
controller now waits for such processes before closing the database. A second
case proves the wait is bounded and an unresponsive helper cannot force database
shutdown. Existing backup, update-cancellation, failed-stop and restart cases pass.

The preceding 4.16.0 candidate failed Mac ARM shutdown after its recovery phase
([run 39251058831](https://github.com/Perseusxrltd/mnemion/actions/runs/39251058831)).
Its uploaded report did not include the process exit/signal or shutdown state.
The controller reproduction above is a measured related defect; it does **not**
establish that failure's cause. New acceptance diagnostics include only the phase,
exit/signal, bounded stage and shutdown booleans. Raw logs, identities and
credentials remain private to the disposable runner.

The next release must independently pass native installation, recovery, clean
shutdown, artifact verification and public upgrades. Check
[release status](../RELEASE_STATUS.md) for delivery evidence. These source checks
do not establish native plugin installation, large-fleet throughput, zero-read
append verification or the availability of a production workspace.
