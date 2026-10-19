# Private desktop connection controls

Source batch: **4.28.0**, 20 October 2026 (Europe/Paris).
See [release status](../RELEASE_STATUS.md) for published installers and native
acceptance. Source checks do not establish that a user's installation updated.

## Problem and implementation

Local agents could control hosting, recovery and updates through the private
desktop pipe, but selecting a remote account still required the interface.
The new operations call the existing connection manager and protected store.
Key activation checks both the expected tenant and principal before publication;
every selection mutation checks the observed connection revision. UI mutation
serialization, draft/request protection and selection notifications are shared
with the existing local recovery controls.

An independent read verifies a supplied key without saving or selecting it.
Status excludes stored credentials and the renderer's native session handle.
Offline account inspection uses its saved, dated identity and recovery record.
Local OS authority remains separate from workspace/space authority.

## Focused checks

**37 connection, password and new operator cases passed**, followed by **10
private-pipe cases**. The new cases cover wrong intended identities, stable and
stale observations, state changes during review, draft refusal, encrypted
persistence across a new manager, offline inspection, rejected reconnect,
unavailable secure storage, password refresh-token custody, partial remote
sign-out failure, device-only forgetting and returning to the local host.
Actual Python/private-pipe exchange and bounded replay/redaction remain covered.
The additional nested-input case verifies password, invitation and key redaction.

These focused storage fixtures use an authenticated test cipher. The installed
gate below exercises real OS protection. No production credential, memory or
host is required for the new tests.

## Installed acceptance

The existing six-target installed recovery gate now creates a disposable reader,
verifies its key without changing selection, rejects the wrong account and an
unsaved draft, and opens that reader through the actual bundled operator client.
It checks UI identity, actual read/write/administrator permissions, absence of
plaintext credentials on disk, stale requests, offline inspection, protected
bookmark reopening, forgetting and return to the independent local owner.
It disables the test principal afterward. These new results are required by
the installed-hosting receipt checker before publication.

The fixture uses an actual local service through the normal saved-connection
path. It does not prove every external company network or signed-in provider.
Company sign-in, invitation enrollment, concurrent multi-workspace sessions and
remote host delegation keep their separate acceptance requirements.

## Published and actual Windows acceptance

Release [4.28.0](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.28.0)
published on 19 October at 23:18 UTC after all six native targets passed.
The user's actual Windows x64 app then updated automatically and selected the
existing shared workspace through `workspace.sign-in`. Its independent human
administrator identity, protected remembered password session and previous
bookmark were verified. See [actual deployment evidence](2026-10-20-shared-workspace-adoption.md).
The automatic release status separately records the public update rehearsals.
