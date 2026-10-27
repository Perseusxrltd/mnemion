# Telemetry development checks and full release qualification — 27 October 2026

The [push selector](../../deploy/ci_scope.py) now recognizes an explicit set of
existing telemetry components and their tests. It does not discover an allowlist
by scanning a changed directory. A new file, shared runtime change, dependency,
workflow, disclosure activation, release route or catalog/wire definition keeps
the full Product checks matrix. Missing Git history, a mismatched checkout,
renames out of runtime paths and non-push/release invocations retain the original
full-check rules.

For a qualifying component-only push, the [workflow](../../.github/workflows/ci.yml)
keeps the full legacy Python and collector suites, Studio/client packaging and
tests, lint/source scanning, dependency auditing, and both Mac Python/Node native
network probes. It omits the service/container matrix and the Mac managed-host,
model and Intel cryptography packaging work. It does not claim installed-device,
whole-application resource or model acceptance from those component checks.

Release preflight and independent verification still require **all 12 Product
check jobs** to succeed, plus the tested same-source Intel runtime artifact.
A component-only push skips five required service/container jobs and produces
no such runtime artifact. The [reuse regression](../../service_tests/test_ci_reuse.py)
also verifies rejection with an apparent artifact present. The unchanged release
workflow requests the full check scope when reuse is unavailable.

**98 source checks passed**, including real Git changes, mixed and unknown paths,
release/manual/PR selection and successful/failed/incomplete reuse evidence.
The first combined pytest invocation stopped during collection because the
service and client directories both contain `test_ci_scope.py`; using importlib
collection resolved that invocation problem. No product check was bypassed.
The checked 111 source inputs remained unchanged, digest
`236985598fb431088f2f815b6e11207c29b237ea5b5a8868a939bf21d47e71c5`.

This is source qualification of selection and release safeguards. No new
workflow run was dispatched to benchmark the optimization, and no measured
time, RAM or CPU saving is claimed. V08 remains Building with production
collection disabled; its acceptance limits and remaining work are unchanged.
