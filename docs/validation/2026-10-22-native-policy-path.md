# Native policy recovery path comparison

The installed qualification on source `38eb3021` reached policy recovery on
Windows x64 and arm64, then failed its combined identity/resource assertion.
Both jobs used a temporary folder under the Windows short-name alias
`RUNNER~1`. The two Linux targets and Intel macOS passed; Apple Silicon did not
acquire a hosted runner. The original
[run and failed receipts](https://github.com/Perseusxrltd/mnemion/actions/runs/39795261005/attempts/2)
remain unchanged.

Native enrollment resolves the selected folder before storing it. Recovery
retains that resolved path exactly. The test incorrectly compared the recovered
path with the original short-name spelling. An actual Windows 3.13.11 Python
check ran the source's `source_folder` function against a disposable directory
and its real Win32 short alias. It verified that both names access the same
synthetic file, resolution changes the spelling, and revalidation retains the
canonical path. The old comparison therefore fails for an unchanged folder.

The [installed probe](../../studio/electron/native-capture-policy-probe.ts) now
checks that the initially saved and selected paths resolve to the same folder,
then requires recovery to preserve that saved path exactly. Policy, source,
grant, pause, resource and single-retirement-request checks remain mandatory.
Failures identify only the mismatched field names, without printing credentials
or captured content. No product path validation or recovery behavior changed.

The corrected Electron build passed. Its initial compile failure, caused by
lost TypeScript narrowing when naming the assertions, remains recorded; an
explicit retained-source check fixed it. The Windows diagnostic used no
production memory or paid model calls and removed its temporary fixture.
Private evidence is in `2026-10-22-windows-policy-path/`.

This diagnosis and build are not installed acceptance. The corrected probe must
complete the normal native matrix before the durable-capture milestone ships.
