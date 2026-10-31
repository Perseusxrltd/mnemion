# Native diagnostic push checks — 31 October 2026

Ordinary pushes confined to the 18 reviewed Windows SDK and Linux BPF diagnostic files now use the existing diagnostic-only check selection. Their native compiler checks remain separately dispatched. Previously these known tool files triggered the full application matrix on each small diagnostic correction.

The selector uses exact paths. Runtime files, unknown siblings, dependencies, release/CI-policy changes and missing or mismatched Git revisions retain full checks. Releases, manual validation and pull requests always retain the full matrix. The unreviewed Mac/ETW prototypes were not added to this allowlist.

The original focused Windows run of `python -m pytest service_tests/test_ci_scope.py --noconftest -q` passed **31 cases in 42.80 seconds**. The cases exercise actual temporary Git histories, mixed runtime files, unknown sibling paths and release/manual/PR behavior. An earlier quoted command was refused before execution; no test was run by that attempt. These tests were not repeated for documentation.

This changes developer check selection, not application behavior, native qualification, release publication gates, telemetry availability or any of the 66 requirement states.
