# Diagnostic database cache restore — 30 October 2026

A manual telemetry diagnostic is a `workflow_dispatch` on an immutable
`diagnostic/telemetry-*` branch. That ref may restore one exact native
PostgreSQL archive. It may not save one. Pull requests stay excluded. Main
and `release/*` restore behavior is unchanged. Only main, after the existing
relocation, TLS, RLS, backup and crash probe, and only on a cache miss, may
write. Windows ARM emulation is still required after that probe.

The key still hashes `.github/workflows/native-runtime.yml` with the compiler
inputs, image and architecture. This condition change is part of that file, so
archives saved before it do not match. The next diagnostic is a cold compile
until a later main build probes successfully and saves. No speedup has been
observed. A miss still builds. No prefix or partial restore key was added.

Astra parsed the changed workflow with the existing PyYAML 6.0.3 environment
and verified that only restore eligibility changed in the parsed workflow.
The cache writer, build/probe conditions and artifact steps are unchanged.
The original Windows parse attempt lacked PyYAML; its failure is retained.
No compiler, app, native check or completed diagnostic was repeated.
