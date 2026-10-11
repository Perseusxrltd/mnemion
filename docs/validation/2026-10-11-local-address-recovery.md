# Local address recovery and Windows installation fixes

These changes are current source, awaiting fresh installed-platform acceptance.
Public downloads remain 4.0.10. No published binary or update feed was replaced
by a development build.

## Integrated installer baseline

[Native run 38158020750](https://github.com/Perseusxrltd/mnemion/actions/runs/38158020750)
at `ac5797b` passed Linux x64/ARM64 and macOS Intel/Apple Silicon: installed local
creation, real model save/recall, automatic workspace reopen, preserved private
credentials and clean database shutdown. Their other packaged checks passed,
including Mac update fixtures and Linux encrypted reconnect.

Both Windows database/private-storage gates passed. Windows x64 reached the
installed local startup but rejected an equivalent PostgreSQL process path.
Windows ARM packaging correctly rejected an ARM `msvcp140.dll` collected into
the emulated x64 service. These two failures are not platform acceptance.

## Windows process identity

PostgreSQL can spell the same directory with different separators, case or
Windows short aliases. Verification now compares filesystem identity, requires
one unambiguous absolute data-directory argument and requires the exact bundled
executable. It retains TLS, data-directory and PID-creation-time checks. A
neighboring directory or another same-named executable is not accepted.

A disposable native Windows 11 build 26200 / Python 3.13.11 test used the real
PostgreSQL archive from that CI run. It started the private server, verified TLS
and its data/process identity, stopped without a remaining `postmaster.pid`,
and reopened the same workspace with alternate path spelling. The old literal
argument comparison was false while the physical identity comparison was true.
All **17** process/port regression tests passed on Windows in **9.19 seconds**.

The source-level test used an ASCII short alias for the certificate path because
stock `python.exe` does not have the frozen product's UTF-8 active-code-page
manifest. It does not establish Unicode-path acceptance of the final installer;
the installed Windows gate must still exercise its actual manifested engine.
No global Python, Windows execution policy or existing installation was changed.

The pipeline now builds the x64 Windows engine once on an x64 runner and shares
that archive between the x64 and native ARM desktops. Source/lock/version,
license, inventory and every binary architecture check remain required. Windows
ARM continues to disclose x64 backend/model/PostgreSQL compatibility.

## App and agent address recovery

The local setup screen offers automatic or explicit API-port selection for a
stopped workspace. A typed local operator command provides agent parity.
Exclusive locking and an atomic settings replacement retain workspace identity,
credentials, model files and RAM policy. Stale sessions cannot overwrite a newer
address; a specified busy port never silently selects a different one. Saving
retains a stopped workspace and requires explicit Resume.

On Linux, process, operator and native-resource tests passed **33 tests**, with
the one Windows-only path test skipped. Tests cover real occupied sockets,
cross-process workspace locking, wrong/stale workspace requests, interrupted
writes, private linked-file refusal and credential-free operator status.
The native-resource tests retain rejection of a wrong-architecture entry point
and a wrong-architecture collected DLL.

The Electron suite passed **66 tests**, including address/start/write exclusion,
status-read serialization, update/close draining and invalid response refusal.
The frontend production build, Python lint, JavaScript syntax, workflow YAML,
pinned action references and whitespace checks passed.

A real Chromium session exercised the built UI with an explicitly disposable
bridge fixture: reserved database port rejection, busy-port errors, retention of
an unsaved choice after an external change, refresh before saving, visible saved
address, no automatic start after Save and exactly one start/open after Resume.
Desktop and 360-pixel layouts were inspected; the narrow layout had no horizontal
overflow. These UI fixtures are not a native database or remote-provider test.

The installed-hosting gate now adds a third launch with its old API port occupied
by an unrelated listener. It must recover through the actual app, explicitly
resume, retrieve the original memory and preserve the same credentials. That
extended installed gate remains pending until its fresh six-platform run passes.

## Remaining release gates

- Fresh Windows x64/ARM installer, real model, reconnect and signed update checks.
- Extended installed address-recovery checks on all six desktop targets.
- Public Linux automatic restart: development diagnostics are separate evidence.
- New release inventories, signatures, notes and public artifact acceptance.

This closes neither organization sign-in/OAuth onboarding nor database-port,
data-location and full backup recovery. The persistent
[requirements checklist](../PRODUCT_REQUIREMENTS.md) retains those tasks.
