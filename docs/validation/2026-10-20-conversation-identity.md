# Conversation identity across a replacement folder

Recorded 20 October 2026 for the next **4.42.0** candidate. The previously prepared
filesystem repair is being combined with this directly related conversation
repair. Neither candidate is published at this checkpoint.

An isolated PostgreSQL workspace and real HTTP service reproduced the defect:
a CLI conversation namespace became a different desktop namespace, creating a
second scope and suspending the original while reporting a completed scan.
The original reader then lost access to the previous memories.

App and native agent setup now accept the original conversation identity, verify
it against the recorded file catalog and retain it in private settings. Unknown
identities, unverified copied bytes and missing original files stop before import. A verified selection
allows normal later deletion, including removal of every file. Existing private
app selections retain their original default on upgrade.

A captured-prefix SHA-256 checkpoint lets a replacement verify its copied bytes
and retain the original capture generation across changed filesystem identity.
The copied-folder test retained the same two memories, versions and reader access
with zero redundant changes. Existing append, rotation, truncation and complete
inventory behavior were exercised in the affected suite.

**52 initial focused Python tests passed**, including real copied-folder reconnection,
missing/wrong identities, unrelated replacement content, complete later removal,
filesystem regression coverage and the existing conversation suites. Final review
found that a partial copy could still suspend other original files. After correcting
that guard, **all 7 conversation identity tests passed**, including refusal of
missing active files, successful completion of the copy, and omission of files
already recorded as `access_lost`. These runs cover 54 distinct cases. The
`access_lost` state can also mean unreadable files; it is not proof of deliberate
deletion. Client,
Electron and frontend production builds also passed, alongside **9 Electron control tests**, including preservation of an existing default conversation identity. Native installer delivery,
cross-platform installed-app acceptance and publication remain separate gates.

An older checkpoint without the captured-prefix hash requires a scan on its
original file with this implementation before copying it. The original inode is
accepted for that transition; an unverified replacement is refused. This does
not recover an unavailable original host or infer an arbitrary namespace from
its hashes. Those limits remain visible in the [setup guide](../service/desktop-sources.md#reconnect-conversation-capture).

The original failure and passing source evidence are separate under
`mnemion-completion/2026-10-20-source-reconnection-review/`: the original
`conversation-observation.json` / `conversation-reproduction.log`, followed by
`conversation-fix-tests.log`, `partial-copy-final.log` and the app build/control logs. The first prepared
filesystem candidate's Mac ARM CI job failed twice because GitHub could not
allocate a hosted runner; its other 11 checks passed. That infrastructure failure
is preserved and has not been relabelled as native acceptance.
