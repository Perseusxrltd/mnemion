# Service and native coverage boundary

The first main check after the encrypted-backup foundation passed all 334
legacy tests but failed its 45% coverage gate: newly added native modules were
counted as legacy code even though their tests belong to `service_tests`.
The failing run is [38653158236](https://github.com/Perseusxrltd/mnemion/actions/runs/38653158236).

The legacy scope now excludes `mnemion/service`, `mnemion/local_*.py` and
`mnemion/backup_encryption.py`. The service suite measures exactly those
families, including native files that were previously outside its report.
The thresholds remain **45% legacy** and **75% service/native**. Shared modules
such as archive publication remain in the legacy scope.

On Python 3.12/Linux, the corrected legacy gate passed **334 tests**, with one
skip and 106 existing deselections, at **48.71% coverage**. The service/native
run passed 995 tests with nine skips; one managed-process test initially failed
because this isolated checkout did not have the pinned `uv` path configured.
Supplying `MNEMION_TEST_UV` and rerunning that test passed with real managed
processes and a verified backup. Its coverage was appended to the original
run, producing **84.78% service/native coverage**, with all 996 executed tests
passing across the two runs. No failing assertion was skipped or weakened.

Local optional real-model, installed-package and client-build checks were not
enabled in this coverage-only checkout. Their existing CI/native release gates
remain unchanged. The published 4.4.0 release independently passed all 30
release jobs and uploaded-artifact verification; it predates the backup source
and does not contain this coverage change.
