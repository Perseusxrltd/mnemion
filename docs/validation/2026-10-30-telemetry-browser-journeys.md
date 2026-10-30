# Browser journey source qualification

30 October 2026. The manual Firefox and WebKit diagnostic is reviewed source;
its actual browser journeys have not yet passed. Production collection remains
off and V08 remains Building.

Actual Grok candidate `29c8ad1fcbcec1acf3a378474c8b241a0d221443` was frozen
when its bounded implementation job ended. Astra corrected the output-directory
handoff, opened the selected search result's collapsed ranking explanation,
and gave the engines separate lexical queries. The content canary now fits
inside a 25-byte packet, so its exclusion check can detect an injected leak.

The first focused source selection passed 32 cases and failed one fixture
directory creation. After correcting creation of the shared parent directory,
that one case passed. These are 33 distinct qualified cases across the retained
original and corrected runs, including the Node driver syntax check. They are
not a final rerun of the complete selection or browser execution evidence.

The [journey design](../implementation/telemetry-browser-journeys-2026-10-30.md)
uses the normal built frontend and a real private memory API. Each engine gets
one fresh profile and one finite journey. Only a successful hosted receipt can
qualify delivery. Playwright WebKit on Linux does not qualify native Safari;
resource and production acceptance remain separate.

## First hosted run

[Run 41005867787](https://github.com/Perseusxrltd/mnemion/actions/runs/41005867787)
used source `35eeebf48673e3a50502575a788bba5fb0553145`. The built frontend
succeeded, but the job stopped with `ValueError: Invalid file descriptor: -1`.
Its uploaded evidence contains the dispatch, source inventory and build log;
no browser result, cleanup receipt or delivery receipt was produced. No browser
delivery or cleanup pass is credited.

Source review found that the static memory marker also appears in bundled
documentation, making the compiled-content assertion unsuitable. The socket's
context also unwinds before the outer Uvicorn cleanup; an exception there can
mask the original failure and prevent receipts from being written. The exact
original failure was not preserved. The correction must use a per-run marker,
keep the listener alive until shutdown, and retain both original and cleanup
errors. The unchanged failed run is not replayed.

## Corrected source

Grok correction `f393edff` generates a 20-byte random marker for each run,
keeps the collector socket open through shutdown, and retains original errors
separately from cleanup errors. Failed cleanup prevents journey qualification.
The 13 focused cases passed on Windows Python 3.13. Grok repeated that selection
while saving its receipt; both original outputs are retained and count as 13
distinct cases, not 26. Astra's formatting change preserved the Python AST.

Review found that a cancellation-resistant task can still delay `asyncio.run`
at CLI exit. A standalone CLI correction remains pending. The hosted command
now has an outer 25-minute timeout with a further 10-second kill grace period,
inside its 45-minute job limit. This lets the artifact step run after a hung
command fails. That external bound permits the corrected functional journey;
it does not claim successful standalone CLI shutdown or collector cleanup.

## Second hosted run

[Run 41008210939](https://github.com/Perseusxrltd/mnemion/actions/runs/41008210939)
used source `e0cacd82edd629841d85df57a57a513bfeda7c25`. Firefox 156.0 and
Playwright WebKit 26.6 both launched. Their unavailable pressure, heap and
network sensors were recorded as unavailable. The collector, memory service,
profiles and private input cleaned up successfully, with no cleanup errors.
Production files remained unchanged.

Neither engine delivered a report. Firefox passed disclosure and manual-review
setup but the probe waited for a setup-choice button after the web app had
already opened its join form. WebKit's immediate `check()` postcondition failed
before the asynchronously persisted checkbox updated; the saved DOM shows it
checked with the expected paused status. Both original errors and zero report
counts remain retained. The probe now accepts the already-open join form and
uses one checkbox click followed by the existing saved-state status check.

Grok's subsequent `72cec66e` replaces the unbounded `asyncio.run` cancellation
gather with a finite wait for leftover tasks. Its new subprocess case keeps a
cancellation-resistant task pending, exits nonzero and preserves the original
error and failed cleanup. The final case passed in 2.92 seconds; the earlier
fixture failure and intermediate output remain retained. This qualifies that
tested CLI path, alongside the existing outer hosted deadline. It is not
browser delivery, resource acceptance, or a guarantee about arbitrary blocked
operating-system calls.

## Third hosted run and control names

[Run 41009303560](https://github.com/Perseusxrltd/mnemion/actions/runs/41009303560)
used source `23835d6f1a0f085f82ef9bf68ebfab263eee6f33`. Both Firefox 156.0
and Playwright WebKit 26.6 passed disclosure, manual mode and workspace join.
Each recorded four successful fixture API calls, then stopped at an exact
`Memory type` label lookup before its first save. No report was received. All
collector, memory API, profile and private-input cleanup checks passed; the
production disclosure and route stayed unchanged.

Grok correction `48e6326c` follows the accessible names present in the original
failure snapshots: the `Memory type` combobox and `Memory content` textbox.
The same wrapped-label issue also affected the later `Search method` select,
which now uses its combobox name. The remaining controls were reviewed against
their actual components. The original Node 25.2.1 syntax command produced no
syntax errors; Astra did not repeat it. The application UI and telemetry rules
are unchanged. This source correction requires the next real browser journey;
it does not qualify delivery or native Safari.
