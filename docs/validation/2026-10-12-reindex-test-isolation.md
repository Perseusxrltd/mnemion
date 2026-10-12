# Reindex test queue isolation — 2026-10-12

The [product run for the 4.1.2 publication documentation](https://github.com/Perseusxrltd/mnemion/actions/runs/38253347261)
reported two intermittent reindex assertions on Python 3.13. Both expected a
worker to find no eligible job. The shared test database retained other tenants'
jobs from earlier tests, including 120-second leases that could expire after a
queue drain. Production workers deliberately claim eligible work across tenants;
a test-only tenant did not isolate those assertions.

The reindex module now uses a separate temporary database for each test, keeping
the real restricted application/worker logins and complete production migrations.
Teardown drops only that specifically created disposable database. This changes
no production worker behavior and weakens no queue, authorization or reindex
assertion. All **13 reindex tests passed**, in 25.32 seconds inside a 768 MiB /
one-CPU scope with no local model downloads.

This test-only correction follows the frozen 4.1.3 commit. The
[complete product checks at that release commit](https://github.com/Perseusxrltd/mnemion/actions/runs/38255848416)
also passed with the original tests. Future main/release runs use the isolated
queue to remove the timing dependence.

The [complete product checks with the isolated queue](https://github.com/Perseusxrltd/mnemion/actions/runs/38258143825)
also passed on `a6e27f8`, including all three Python versions and both Macs.
