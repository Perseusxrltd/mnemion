# Injected fixture owner

This is a manual Mac program. The compile-only workflow does not build or
start it. The separate manual workflow
`.github/workflows/macos-keychain-injected-fixture.yml` is the first
compilation lane for this owner. It stays inactive until Astra dispatches it
after review. It is not wired to push, pull request, or workflow_call. The
commands below were not run while this file was written. Behavioral checks
were not run. GitHub Actions run `41346487519` does not cover this owner.

The typed command starts the supervisor in `fixture_owner.c`. The supervisor
does not open, stat, unlink, or fsync the fixture tree. It does not call
`getpgid`. Its normal budget is 60 seconds of `CLOCK_MONOTONIC`, measured from
before `posix_spawn` of the owner. That budget is not the owner's own clock.
The owner starts a separate 60-second clock when its `main` work begins, and
that clock covers the worker builds and the cases. Each owner child wait is at
most 10 seconds and does not move the owner's deadline. When the owner tells
the supervisor that cleanup has started, or when the supervisor's 60 seconds
end first, the supervisor allows a cleanup grace of 10 seconds. The owner's
cleanup grace is also 10 seconds, and it is checked again before every
cleanup entry.

A deadline, a `SIGKILL`, or the supervisor returning is not evidence that a
process stuck in the kernel was reaped. `kernel_stuck_reaped=0` on every
supervisor line. `decision_reaped=1` means `waitpid` collected that direct
child before the deadline decision was fixed. A `waitpid` after that decision
is only a short hygiene collect. `ESRCH` from `kill(-pgid, 0)` means that
probe saw no member of the retained group. It is not `waitpid`, and it is not
permission to signal that number after it has been seen empty.

When the owner has observed `ESRCH`, it sends one `X` record and drops that
number from its own signal list. The supervisor's later probe is a separate
observation. An `X` record retires that numeric group from every later
supervisor `SIGTERM` and `SIGKILL` for the rest of that supervisor process.
If the supervisor's probe still sees a member, or the probe is uncertain, the
outer result stays unresolved. The retired number is still not signaled.
Agreement that a probe saw nobody does not mean a later process with the same
number is the same group, and it does not make that number a signal target
again.

The owner stops only retained process groups. A group id is the child pid
returned by `posix_spawn` with `POSIX_SPAWN_SETPGROUP` and a new group of 0.
Reaping the leader does not drop that record. Cleanup cannot complete while a
retained group still has a member, while a probe is uncertain, or while a
reported directory is still open in the supervisor's record. The owner does
not kill broadly, and it does not touch a login Keychain or a search list.

Run the commands from the repository root. `$PARENT` is an absolute private
directory created for this run. It must not be the current directory, must
not contain or sit inside the current directory, and must not contain a
symlink component. `/tmp`, `/var`, `/private/tmp`, `/private/var`, and any
path under `Library/Keychains` are rejected. The owner creates a new directory
inside `$PARENT`. It does not reuse, chmod, or delete a pre-existing user path.

The file `throwaway.keychain` is created with the bytes `not-a-keychain` and
a newline. It is not a Keychain. The sealed header is written before each
worker build. The same sealed directory is reused for the two process-restart
children. That pair is process-restart evidence. It is not a power-loss
experiment.

## Intel

```sh
clang -arch x86_64 -mmacosx-version-min=13.0 -std=gnu11 -Werror -Wall -Wextra -Werror=implicit-function-declaration -o "$PARENT/fixture-owner" deploy/macos_keychain_proof/fixture_owner.c
"$PARENT/fixture-owner" x86_64 "$PARENT"
```

## ARM64

```sh
clang -arch arm64 -mmacosx-version-min=13.0 -std=gnu11 -Werror -Wall -Wextra -Werror=implicit-function-declaration -o "$PARENT/fixture-owner" deploy/macos_keychain_proof/fixture_owner.c
"$PARENT/fixture-owner" arm64 "$PARENT"
```

That command is the supervisor. It then spawns the same binary as
`fixture-owner --owner <arch> "$PARENT"` in a new process group, with the
record pipe on fd 3. Two other modes exist only as children of this program:
`--stall-child` and `--descendant-leader`. They are not the manual command.

Before the 60-second clock starts, the supervisor runs one stall check. The
child ignores `SIGTERM` and stays in `pause`. The check's own normal budget
is 400 milliseconds, starting after that child has been spawned, and its
cleanup grace is 200 milliseconds. The expected
decision is `decision_reaped=0`, `cleanup=incomplete`, and `custody=retained`.
That decision is fixed before `SIGKILL` and those three fields stay as fixed.
They are not rewritten if a later hygiene `waitpid` collects the child.
`hygiene_collected=1` means that separate `waitpid` collected the stall child.
`hygiene_group_empty=1` means `kill(-recorded_pgid, 0)` then returned `ESRCH`.
Neither field, nor `SIGKILL`, nor the time spent waiting, proves that a
kernel-stuck process was reaped. The supervisor spawns the owner only when
the frozen decision matched and both hygiene fields are 1. If the frozen
decision did not match, it exits 1 and does not spawn the owner. If the
decision matched but hygiene did not confirm the child and the group, it
exits 2 and does not spawn the owner.

The owner then runs the wrapper cases, one replaced-entry cleanup case, and
one descendant case. The replaced-entry case renames a directory it created,
puts a regular file and then a symlink at the old name, and requires
`remove_tree` to leave both in place. It also replaces a child directory and
requires the old device and inode to be refused. The descendant case is the same single check. Its leader forks one child in
the same retained group. The child installs `SIGTERM` ignore and writes one
acknowledgement byte. Only then does the leader write the six-byte frame
`ready\n`. The owner accepts that frame without waiting for end of file. The
child ignores `SIGTERM`. After the leader is reaped, cleanup must still be
refused while that group has a member. Cleanup then sends `SIGKILL` and
watches the retained group for at most two seconds inside the existing
10-second cleanup grace. If that capped observation or the grace ends first,
cleanup stays incomplete. `SIGKILL`, elapsed grace,
and disposal of the runner are not proof the kernel reaped the child. These
three checks are owner checks. They do not add wrapper cases.

## Worker compile the owner spawns

For each sealed run the owner runs `clang` with `-arch` set to the same
architecture, `-mmacosx-version-min=13.0`, `-std=gnu11`, `-fno-objc-arc`,
`-fblocks`, `-DOS_OBJECT_USE_OBJC=0`, `-DMNEMION_FIXTURE_INJECT=1`,
`-DFIXTURE_ARCH` set to `arm64` or `x86_64`, `-DFIXTURE_SOURCE` set to the
40-character `git rev-parse HEAD` value, `-Werror -Wall -Wextra
-Werror=implicit-function-declaration`, `-I "$RUN/include"` before
`-I deploy/macos_keychain_proof`, and `-framework CoreFoundation -framework
Security`. The sources are `fixture_worker.c`, `fixture_inject.c`,
`fixture_store.m`, `fixture_store_syntax.c`, `parent_direct_lookup.m`,
`key_item.m`, and `v10_crypt.c`. The output is `$RUN/worker`. The owner then
runs `nm -g` on that binary and refuses the named Security entry points.
Ordinary helper and compile-only builds do not pass `-DMNEMION_FIXTURE_INJECT=1`.

There are five sealed runs, so there are five worker compiles inside the
owner's 60 seconds. Each of those compiles is one child wait of at most 10
seconds. A slow compile is a test failure. It is not a reason to raise the cap.

## Results

Stdout is categories, counts, and synthetic ids. A passed expected refusal,
a test failure, and incomplete cleanup are different verdicts. The supervisor
exit status is the outer result. Exit 0 means the stall hygiene confirmed its
own child and group, the owner exited 0, `waitpid` collected the owner inside
the budget, every retained group probed `ESRCH`, and every directory record
the supervisor received was cleared by the owner's own claim. Exit 1 means
the stall deadline was not the expected frozen decision, or a test failure
after settlement. Exit 2 means cleanup or settlement stayed incomplete,
including a timeout and a stall whose hygiene did not confirm the child and
group. Exit 3 means the run was cancelled or the owner exited 3 after
settlement. Exit 4 means usage or preflight rejection after settlement. The
summary line always includes `deadline_does_not_prove_stuck_kernel_reaped=1`.
The stall line's frozen `cleanup=incomplete` is not the outer `case=supervisor`
cleanup field.

## Custody and deadline limits

The supervisor can establish only what its own clock, `waitpid`, and retained
group probes show:

- whether it returned inside the 60-second normal budget and the 10-second
  cleanup grace
- whether `waitpid` collected the direct owner or stall child before the
  decision was fixed
- whether `kill(-recorded_pgid, 0)` returned `ESRCH` for a group id recorded
  at `posix_spawn` or received on the record pipe before that probe
- the owner's exit status when that `waitpid` collected an exit
- that a directory record was still present because no matching clear record
  arrived

The supervisor cannot establish:

- that a kernel-stuck process was reaped
- that a process group id is the same group after `ESRCH`; it does not signal
  a group after that probe, and it does not look up a new group
- that the owner's `X` record and the supervisor's probe are one observation.
  `X` retires the number. A disagreeing or uncertain supervisor probe keeps
  the result unresolved and still does not signal that number
- that an unreported child, grandchild, or directory was settled
- that fixture files are gone; it never inspects them
- that the owner's clear record is true; a clear record drops only the
  supervisor's copy of that claim

Removal compares the recorded device, inode, and type of every opened
directory, and compares the directory entry again immediately before
`unlinkat`. A failed open is not removed. A mismatch keeps the held directory
fd when the owner still has it and leaves cleanup incomplete. The comparison
and `unlinkat` are not one kernel operation. A replacement that appears after
the check can still be removed. Uncertain identity keeps custody. If the
replaced-entry case cannot remove the regular file or the symlink it created
at the old name, cleanup uncertainty stays set. A later removal of the
original directory does not clear it, and cleanup cannot complete.

The owner writes `custody-<id>` under the private parent only when its own
cleanup attempt cannot finish. The supervisor does not write that file. If
the owner is blocked in the kernel, the supervisor prints `custody=retained`
and does not claim the custody file exists. The pid and pgid in that file are
the ids recorded at spawn. They are not a later signal target.

A record write that cannot complete, or a child created before the record is
written, is invisible to the supervisor. The owner then keeps cleanup
incomplete. The supervisor still cannot see a child that was never reported
and then became stuck.

Signal wakeups use a nonblocking self-pipe. `EINTR` is not treated as
settlement. `GitHub Actions` run `41346487519` remains an earlier
compile-and-link receipt. It does not cover this owner.

## Manual workflow inputs

File: `.github/workflows/macos-keychain-injected-fixture.yml`.

Astra dispatches it after review. Nothing else starts it. The job cap is 10
minutes. There is no native retry. The job does not call `codesign`,
`security`, `launchctl`, or a default-store API.

Inputs:

- `source`, required string. Exactly 40 lowercase hex characters. The job
  checks out that commit, then refuses to compile or execute unless
  `git rev-parse HEAD` is that same value.
- `target`, choice, default `arm64`. The only choices are `arm64` and `x64`.
  `arm64` selects runner `macos-26` and clang `-arch arm64`. `x64` selects
  runner `macos-15-intel` and clang `-arch x86_64`. No other runner is used.
- `run_fixture`, boolean, default `false`.

`false` compiles this owner with the clang flags in the Intel and ARM64
sections above, and compiles the helper, parent, and identity tool by running
`compile_only.sh --compile-only` with that script's current pin and source
inputs. It executes none of those newly compiled binaries.

`true` is a later explicit selection of the supervised command in those same
sections, `"$PARENT/fixture-owner" arm64|x86_64 "$PARENT"`. The job keeps
that process's exit status and the outer `case=supervisor` `cleanup=` field.
Any exit other than 0, or an outer cleanup other than `complete`, fails the
job. The stall line's frozen `cleanup=incomplete` is not that outer field.
`SIGKILL`, elapsed time, and runner disposal are not recorded as kernel
reaping.

`$PARENT` is a new directory under `RUNNER_TEMP`, outside the source tree,
and it must pass the parent rules above. Compile status and compiler logs are
one artifact. Fixture stdout and fixture status are a separate artifact, and
only when `run_fixture` is true. Those artifacts keep the requested source,
architecture, compiler status, and fixture evidence. They do not keep
credentials, the disposable store file, or linked binaries.
