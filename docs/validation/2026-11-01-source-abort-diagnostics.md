# Directory and journal abort receipts

1 November 2026. Source base `212c7d445d3427e80dcaddbb80b7eba4e4aad80e`.
Validated for the next release after 4.46.63. Publication and platform results
are tracked separately in [release status](../RELEASE_STATUS.md).

The 29 October file-receipt work left two abort paths outside the incomplete
inventory receipt. A directory read failure dropped the path and operating-system
category. A directory symlink or junction raised `source_symlinks_not_supported`
before a file receipt existed. A skipped `.json` or `.jsonl` became
`journal_inventory_unreadable` and lost an access-stop's original category and
path. A later root access refresh could clear that suspension without a durable
failed inventory. Those original gaps stay recorded in
[the 29 October note](2026-10-29-source-read-diagnostics.md).

This change sends those access stops through the existing owned-run finish.
The receipt keeps the fixed category and, when the relative path passes the
512-character safe-path rules, that path and its SHA-256. An unsafe path is
omitted. Host paths, link targets, operating-system text, and file bytes are
not stored. The previous checkpoint stays. The finish is not a complete
inventory, so it does not infer deletions or acknowledge a requested sync.
Items this run did not re-read are withheld, including after a root-only
refresh. A body-free retain does not clear the hold. A later complete scan
restores unchanged items and leaves the failed run's receipt in history.
Readable malformed journal text still raises a journal error and is not an
access hold.

A later correction keeps the stopping access category inside the 50-entry
receipt, suspends that owned run inside the same finish, and omits an
unencodable relative path without dropping the category. An authorized replay
of the completed finish returns its saved receipt, including while that finish
has suspended the source. It cannot suspend a later runner's lease or bypass
the active-access check for an unfinished run.

**All 24 focused checks passed in 65.19 seconds.** They used temporary source
trees and a disposable PostgreSQL database, with its matching client tools.
The complete source-health test file covers the shared finish, access holds,
bounded diagnostics and receipt replay. Four targeted provider cases cover
directory links, safe and unencodable paths, and journal access stops:

```
pytest -q --tb=short --color=no \
  client_tests/test_connector_providers.py::test_folder_symlink_cannot_escape_selected_vault_or_certify_deletions \
  client_tests/test_connector_providers.py::test_unreadable_directory_keeps_a_safe_category_and_omits_an_unsafe_path \
  client_tests/test_connector_providers.py::test_unencodable_directory_name_keeps_the_category_and_a_real_path_keeps_its_hash \
  client_tests/test_connector_providers.py::test_journal_access_stop_keeps_its_receipt_and_projects_nothing \
  service_tests/test_source_health.py
```

The changed Python files passed lint after removing an unused test-fixture
binding; the save operation itself was retained. OpenAPI and the agent
contract were regenerated with the canonical service commands. The client
and app TypeScript checks passed. The first app check used an older client
package through the review environment's shared dependency symlink. Only
that failed check was repeated, with the freshly built candidate declarations;
no product-source change was needed for it. Original results were retained.

The source was reviewed through Grok commit
`7c1f13861286d99a652e2c5f2d9d9c7839c18039`, then integrated with the
[separately validated Git-cache recovery change](2026-11-01-git-cache-restore.md).
These checks establish the local source-access contract. They do not establish
recovery of unavailable live sources, reporter-device behavior, platform
installer acceptance or the rest of GitHub issue #47.
