# Split concatenated transcripts

`mnemion split` separates concatenated Claude Code `.txt` transcripts before
mining. It scans the given directory, without descending into subdirectories,
for `Claude Code v` session headers. Nearby context-restore markers are not
treated as new sessions. The default threshold is two sessions; fragments shorter
than ten lines are not written as session files. Keep the original as the complete
recovery source.

This guide describes the [27 October source correction](../validation/2026-10-27-split-preservation.md).
Consult [release status](../RELEASE_STATUS.md) for published availability.

## Preview, then apply

Preview the proposed files without changing anything:

```sh
mnemion split ./transcripts --output-dir ./split-sessions --dry-run
```

Apply the split by omitting `--dry-run`:

```sh
mnemion split ./transcripts --output-dir ./split-sessions
```

Omit `--output-dir` to write beside each input file. Missing output directories
are created only when applying a split. Use `--min-sessions N` to change the
selection threshold. Dry-run creates no output or backup directory and leaves
source files and existing backups unchanged. Proposed names can change if other
files appear before the real run.

Output names use the source stem and detected session metadata. If a name already
exists, the splitter reserves a different name with a suffix such as
`__part02` or `__part02_2`. Exclusive creation protects existing files even when
another writer takes the proposed name first. Inputs and outputs use UTF-8;
undecodable input bytes are replaced in the derived session text. The archived
original retains its original bytes.

## Where originals go

After all selected session outputs for one input have been written, that input
moves into a newly reserved private `.mnemion-split-backup-*` folder beside it.
For example, `transcripts/sessions.txt` is archived as:

```text
transcripts/.mnemion-split-backup-<unique>/sessions.mega_backup
```

The command prints the full archive location. The archive stays beside the source
even when outputs are on another drive; moving the original uses a rename on
its own volume. Existing `.mega_backup` files and older backup folders are left
untouched. These dot-prefixed folders may require showing hidden files in your
file manager.

## If processing stops

A failed output write leaves that input unarchived. Files written earlier in the
operation, including a partial output from an I/O failure, can remain. If an error
occurs around the archive move, check both the source path and the newly created
backup folder for the original. The splitter does not recursively remove recovery
data or automatically retry the failed action.

Use the original to recover, rather than assuming partial outputs are complete.
Review and set aside those outputs before another attempt; use a copy of the
original and a separate output directory, starting with dry-run. Earlier inputs
in a multi-file batch may already have been archived successfully.

Splitting is not an all-files transaction and does not snapshot a source that
another program is changing. Finish transcript recording or work from a stable
copy before applying the split.
