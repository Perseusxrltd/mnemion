# Windows private folders and concurrent backup reads

Recorded 29 October 2026 for **4.46.53 source**.

The 4.46.51-r2 native run `40835999398` failed its Windows ARM installed backup
resume check with the existing safe-read refusal. The original failure remains
retained. Its disposable runner's private files were not retained, so the exact
trigger of that particular failure is unresolved. The earlier Linux failure is
also not retroactively explained by this Windows result.

A separate actual Windows reproduction found a concrete defect:
`state.directory()` reapplied an identical protected folder DACL, and Windows
propagated it to an inherited `backup-policy.json`. Its change time moved while
its bytes, identity, size and modification time stayed unchanged. Calling the
real Python helper between the TypeScript reader's path and descriptor checks
therefore caused the original reader to refuse the file deterministically.

`mnemion/private_output.py` now inspects the current handle's DACL on every
call. It skips a rewrite only when that DACL is protected, non-defaulted and
contains exactly the expected owner ACE, rights and inheritance flags. Broader,
unprotected, null or incorrectly inheriting DACLs still get repaired and checked
again. Inspection failures still refuse access; there is no permission cache.
The existing ownership, junction and file-integrity boundaries remain in place.

The corrected native regression keeps the inherited child's change time stable
and completes the same read. Windows checks use the actual NTFS change time;
Python 3.13's `st_ctime` on Windows is a creation time and is not that evidence.

| Focused qualification | Result |
| --- | --- |
| Windows Python 3.13: private folder and local-state checks | 20 passed, 3 platform/elevation exclusions |
| Linux Python: local-state, private-output and state reads | 22 passed, 13 Windows exclusions |
| Windows Node 25.2.1: final backup, replacement, diagnostic and signing-policy cases | 39 passed, 4 POSIX-only exclusions |
| Linux Node 22.22.0: backup, replacement and diagnostic cases before the final Windows-specific case was added | 38 passed, 2 Windows-only exclusions |
| Electron TypeScript build with locked dependencies | Passed |

The new cross-language Windows regression is included in the final 39-case
passing Windows result. These local fixtures do not replace the required
packaged Electron and six-target release validation.

Backup-state failures now carry three fixed fields: document category, read
stage and filesystem-error category. The installed-test artifact validates that
small schema again; arbitrary fields, paths, settings, error messages and stack
traces are excluded. The ordinary user error and retained recovery files are
unchanged. The new diagnostic is failure evidence, not anonymous usage collection.

| Retained evidence | SHA-256 |
| --- | --- |
| Original Windows reproduction | `d9d4d6a1bd9824651efdb982ccaf260d59acb9cb0703fc503f26605b9eaccc13` |
| Corrected Windows reproduction | `e2b9bd220c0f91cb0510b60fea79d194c113653482dea03e593e6c4ca0033261` |
| Windows Python receipt | `2049500fd58be6b7b1064d70b7f39d953362d6ff22becb6f2a87feee826b6a77` |
| Windows Python input manifest | `932dcb616224a06055b69ac48084207560a82ea928e4772cf546160b8be7c0e5` |
| Linux Python receipt | `c38a137d8c287d413a309dce07f7a511ffb7a6d08e3563c890f2cb1b99a0b62e` |
| Final Windows JavaScript receipt | `5cdeb0e8392649f8a7e674efc09f6499bf79e9a677108902a739848415925d83` |
| Final Windows JavaScript input manifest | `08706a6cf160b3c6ee5fa53bca1a3731945fa27d9a1710200a95dd0b5704986c` |

The preliminary corrected reproduction's `sourceCodeUnchanged` field refers
only to the unchanged TypeScript reader; its Python permission helper was
corrected. The original receipt is preserved with that limitation stated here.
Native release acceptance remains pending. No production workspace or recovery
files were changed by these synthetic checks.
