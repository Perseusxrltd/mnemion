# Owned-launch accounting source qualification

30 October 2026. The resource-accounting adapter is diagnostic source. It has
not yet qualified native lifecycle behavior or measured installed app overhead.
The 8 MiB additional RSS allowance per participating process and 0.5% of one
CPU core remain unaccepted. Production collection stays off.

Grok's original `7a7f5802`, first correction `7b5f5835`, and reviewed correction
`d0425efd` remain separate commits. Astra's review required Darwin's `wait4`
to own direct-child reaping, correct float-second CPU conversion, verified
process-group cleanup after root exit, correct libproc empty/error semantics,
a frozen launch identity, and rejection of actual cleanup failures. Those
source findings are resolved. The 13 focused non-lifecycle checks passed on
Windows; Astra retained the original output and applied formatting with an
unchanged Python AST. No duplicate lifecycle run was used for this review.

The [manual native workflow](../../.github/workflows/telemetry-owned-launch.yml)
runs the self-check once on each of the six existing native targets and retains
its source, launch mode, receipt and errors. It builds no installer or model.
The adapter owns the process group before releasing its child, and the observer
stays outside that group. Failed or missing cleanup prevents qualification.
The intentional invalid-handle exercise remains separate from real cleanup.

Windows uses job accounting that includes exited processes. Linux requires a
disposable delegated cgroup; unavailable support is recorded without claiming
qualification. macOS uses direct-child wait accounting and remains partial for
descendant CPU coverage. Missing counters stay missing. Commit, footprint and
cgroup memory totals are not substituted for RSS.

The native group query is bounded to 64 entries and rejects a full buffer as
incomplete. PID reuse does not replace the original launch identity or authorize
signaling another group. Native receipts are required before attaching this
adapter to the existing 128-cycle installed workload and its fixed counterbalance.
No resource-budget pass follows from these source checks.
