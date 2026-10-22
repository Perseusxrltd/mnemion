# Dated validation reports use documentation push checks

Reviewed **22 October 2026**. Documentation commit
`200a09eaee5f7f4a0bd553d52ddf80325e7beb00` added a dated JSON native-acceptance
receipt alongside five Markdown guides/reports. The existing selector treated
that JSON report as an unknown runtime file and scheduled the full service
matrix in [run 39842066124](https://github.com/Perseusxrltd/mnemion/actions/runs/39842066124).

The selector now recognizes flat `YYYY-MM-DD-name.json` reports under
`docs/validation/`. API schemas, nested fixtures, workflow/dependency changes,
unknown JSON and removed or renamed source files still select runtime checks.
Lint and Studio, including client tests and the packaged documentation build,
remain required for documentation pushes. Release, pull-request and manual
checks always retain the full matrix or the independently verified release
reuse contract.

The focused classifier suite first reproduced three failures, then passed all
**21** cases after the correction. Replaying the actual six-file commit diff
selected `documentation_only`; the same source with the release flag selected
`release_or_non_push` and all runtime checks. This replay did not dispatch CI.
All **42** focused release-check reuse tests also passed.
The source change itself requires normal full source checks.

The frozen **4.45.0** candidate and its running artifact verification are
unchanged. This improves future evidence publication; it neither qualifies a
release nor resolves GitHub's separately observed delayed job metadata.
