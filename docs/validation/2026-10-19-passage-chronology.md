# Passage chronology, recent relevance and identifier questions

Source batch: **4.14.0**. The batch addresses the concrete multi-topic decision,
cosmetic-edit and weak-newest-hit cases reported in issues 17 and 31. It does
not claim general natural-language quality, full contradiction resolution or
reconstruction of historical Git blame.

The focused search, passage, source grouping, question, SDK, evaluation and
company-upgrade selection passed **103 cases in 45.18 seconds**. Historical
preimage fixtures were updated to use the frozen preceding revision writer
instead of invoking a new-column writer against an old schema. The separate
historical migration, installed-inventory, backup and host-recovery selection
then passed **39 cases in 83.47 seconds**, including schema prefixes 13–20.
After the final source-date guard, the affected ranking and chronology suites
passed **43 cases in 15.44 seconds** at version 4.14.0.

Evidence includes:

- The specific decision in an eight-topic Markdown row ranks first for a
  natural-language question containing its ID, under both relevance and recent
  ordering. Identifier boundaries, explicit syntax and user thresholds remain.
- A later timestamped correction ranks before an older statement even when
  both files report the same modification time. Context follows the same order.
- Whitespace and unrelated edits preserve a status passage's earlier date;
  a changed statement under an existing date heading receives its update time.
  Real connector ingestion retains source/memory identity across the change.
- Recent ordering demotes a weak newer README while retaining it in the result
  set. The strict-date control restores chronological order without changing
  rank-fusion scores. A real recorded evaluation measures both outcomes.
- Dates inside fenced code, inline deadlines, invalid/future labels and unknown
  timezones do not become invented precise timestamps. Original Unicode offsets
  are preserved, and excessive passage counts report the whole-record fallback.
- Python search, context and evaluation requests omit unsolicited new nested
  settings for older servers. Explicit overrides remain available.
- The installed-upgrade inventory normalizes only the missing historical empty
  chronology field. An actual changed field, key marker or original memory row
  still changes its preservation hash. Existing keys, grants, source data and
  author withdrawal survive the schema upgrade.
- Existing encrypted backup and complete host reconstruction continue to work
  with the new revision column, without resetting workspace identities.

The TypeScript client, production web app and Electron builds passed at 4.14.0
with the new search and evaluation controls. Both dependency locks, release
version metadata, generated API/agent contracts and Python lint checks passed.
Native publication and public automatic upgrades are
separate gates tracked in [release status](../RELEASE_STATUS.md).

Tests use temporary PostgreSQL databases and synthetic sources. The deterministic
fixture embedder verifies protocol and ordering behavior; it is not a benchmark
of a production embedding model. No production workspace content was copied or
changed. The one additional authorized content query is capped at 250 candidates;
CPU/memory costs on representative large live workspaces remain to be measured.

The preceding [4.13.0 Windows x64 gate](https://github.com/Perseusxrltd/mnemion/actions/runs/39230702617/job/117994019622)
expired after four minutes. The initial app exited normally, the installed ASAR
already contained the target version, and the NSIS process still existed, but
native extraction was incomplete and no relaunch was recorded. This establishes
an incomplete installation at the deadline, not its cause. Windows ARM completed
the same unchanged-source gate.

The 4.14.0 rehearsal now records bounded installer CPU/IO samples after two
minutes. Measured progress can extend the four-minute window; two minutes with
no progress fail it, and ten minutes is the absolute ceiling even for a spinning
process. Version, new process, complete native binary hashes, authentication and
restart-guard assertions still apply. Three focused scenarios check stalled,
slow-progress and continuously busy cases. This changes CI observation only;
it does not claim to repair or explain the original installer stall. The queued
first 4.14.0 attempt was cancelled before execution so a corrected immutable
candidate can run once.

The Electron build and its **187 tests** passed with this observation change,
including the three progress-window scenarios. Native Windows PowerShell parsed
the observer successfully; release metadata and patch whitespace checks passed.

The corrected [4.14.0 release run](https://github.com/Perseusxrltd/mnemion/actions/runs/39236264889)
passed all 32 jobs, including all six native targets. Independent
[uploaded-artifact verification](https://github.com/Perseusxrltd/mnemion/actions/runs/39241687200)
passed and published the release on 19 October at 11:03:23 UTC. The
[website update](https://github.com/Perseusxrltd/mnemion/actions/runs/39241852486)
also passed. Public automatic upgrades have their own recorded workflow in
[release status](../RELEASE_STATUS.md); the earlier installer stall's cause
remains unproven.
