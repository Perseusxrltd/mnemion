# Desktop journal host setup — 19 October 2026

The 4.18.0 source adds app-owned host registration for Git journals. All test
workspaces, repository URLs and queued memories are synthetic. No user
installation, office workspace, personal memory source or remote repository
was changed by these checks.

**36 Python checks pass**: 16 journal cases including a real PostgreSQL service
case, and 20 existing local readiness/address checks. The journal cases cover
private registration, derived storage locations, unchanged workspace identity
and preservation of existing sign-in files. They reject stale or foreign requests,
host paths, executable programs and URLs containing credentials. They also cover
duplicate destination folders, external configuration and explicit repair.
The actual CLI refuses credential-bearing URLs without reflecting their contents.
Removal retains private queue files; damaged-record repair retains exact bytes.

The service case registers a destination without enabling publication, explicitly
approves it, and saves a memory with a durable private receipt. Changing the folder
then blocks further journal-backed saves until fresh approval. Both the original
memory and queue survive the change; another approved save is durable. The test
uses paused publication and makes no external Git request. Existing journal tests
remain responsible for real Git delivery, concurrent writers and remote receipts.

**63 desktop controller/operator checks pass**, including five new cases for the
registration handoff, drain/reopen, stale edits, explicit stop and a mismatched
repository response. The TypeScript process compiler, library, web renderer and
Electron renderer build successfully; offline lock and source checks pass.
The compiled local agent catalog exposes 26 operations, including `local.journal`.

The installed-hosting probe now uses the actual registration form, waits for its
controlled service restart, checks the saved destination and confirms that space
publication remains unapproved and an existing memory remains readable. This
new native flow still requires the release pipeline's six-platform acceptance;
source/controller checks are not evidence that the native run has passed.

Installation, independent artifact verification, publication, website refresh and
public automatic upgrades are tracked in [release status](../RELEASE_STATUS.md).
This batch does not establish Git credential-manager sign-in, live-provider write
access, arbitrary remote-host setup, automatic host-settings recovery or production
workspace availability.
