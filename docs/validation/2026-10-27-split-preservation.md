# Transcript output and original preservation — 27 October 2026

This hotfix is based on `149a384a97a8cc0aeded31cfb987fa0a9bbc6ecd`.
The [splitter](../../mnemion/split_mega_files.py) previously reused generated
filenames and the adjacent `.mega_backup` destination. Two retained synthetic
temporary-file probes showed two sessions collapsing into one output, and an
existing backup being replaced. They used no user or production memories.

Four original selected tests also failed: duplicate session names, an occupied
output path, an existing backup, and a missing output directory. These failures
remain separate from the corrected results.

## Corrected boundaries

Session files are opened with exclusive creation and disambiguating suffixes.
A filename collision, including one caused by a racing writer, selects another
candidate; write/close failures do not retry the action. Missing output directories
are created only on apply. Transcript reads and session writes explicitly use
UTF-8, retaining the existing replacement behavior for undecodable input bytes.

After successful output writing, each original moves into a newly reserved
private `.mnemion-split-backup-*` directory beside its source. Its original
`.mega_backup` filename is used inside that directory, and the full location is
printed. This is a same-volume rename, with no hard-link requirement. Existing
legacy backups remain untouched. On a failed archive move, cleanup attempts only
to remove the empty reserved directory; it never recursively deletes recovery
data.

Output failure leaves the original unarchived. Injected errors before and after
the rename verify that its bytes survive at the source or in the new backup.
Partial or earlier completed output files can remain after I/O failure. There is
no all-files transaction, automatic action retry or snapshot guarantee for a
concurrently modified source. Dry-run creates no output
or backup folder and preserves the existing files. The
[user guide](../guides/transcript-splitting.md) explains inspection and recovery.

## Scoped validation

The corrected actual temporary-file tests and existing classic CLI checks exited
successfully: **72 passed in 8.01 seconds**, comprising **14 splitter tests and
58 classic CLI tests**. The [splitter tests](../../tests/test_split_mega_files.py)
cover collisions, UTF-8 contents, a controlled racing writer, existing backups,
directory creation, output failure, before/after-move errors and dry-run.

All **856 recorded runtime/test inputs** matched after the final source tests,
before release-version preparation, with digest
`73743ef6ba0eda7a1779f0aca8841ea875a8ad4a6b073a40bf503a6476fb11c8`.
The retained passing log has SHA-256
`99e28092d1cf2122132941ccaab7678592c7b522b58ef2af3c92210bec241a83`.
The earlier two probes and four failing tests remain retained.

The initial 72-pass stage remains retained. Final review avoided joining transcript
text during preview and repeated directory creation; the same focused suite then
passed on that final source. These are 72 distinct checks, not 144. The later
4.46.39 preparation changed only eight version-metadata files in this inventory,
verified against their original bytes; no behavior test was repeated for the
metadata change.

No new dependency, model execution, app/resource/platform journey or telemetry
category was added. `split` and `llm test` remain unmeasured. This source result
does not establish release or installed-platform acceptance. All 66 requirement
states and existing privacy/resource/release gates remain unchanged; V08 stays
**Building**, production collection/destination/route **false/null/null**, with
empty release CAs and unchanged resource ceilings.
