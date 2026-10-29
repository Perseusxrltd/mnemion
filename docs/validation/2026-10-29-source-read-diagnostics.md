# Actionable failed source inventories — 29 October 2026

Issue 47, comment 6501377042, describes service 4.46.52. A selected ordinary Markdown file was unreadable by the runner account. The scan failed as `source_unreadable_or_symlink_changed`. A refreshed access lease could hide that warning even though no inventory completed.

This change classifies the operating-system error and keeps only a fixed code. It does not copy `strerror`, `filename`, or `winerror`. Python 3.12 maps `EACCES` and `EPERM` to `PermissionError`, and `ENOENT` to `FileNotFoundError` ([Built-in Exceptions](https://docs.python.org/3.12/library/exceptions.html#os-exceptions)). Linux `open` with `O_NOFOLLOW` fails a trailing symlink with `ELOOP`, which stays a plain `OSError` ([open(2)](https://man7.org/linux/man-pages/man2/open.2.html)). The link category therefore uses `errno`.

The first file that stops the scan is stored on the incomplete inventory as a source-relative path of at most 512 characters and the SHA-256 of that path. Absolute paths, `..`, backslashes, and control characters are dropped. The scan does not continue, does not certify deletions, and does not advance `completed_at`. After that receipt the scope suspends. A later access refresh clears the suspension. It does not remove the receipt or move the last completed scan. OpenAPI `info.version` stays `4.46.53`.

Checks used the pinned release environment, Python 3.12.3 (GCC 13.3.0), from this clone on 29 October 2026. No separate Windows account and no installed service were used. Permission denial is an injected `PermissionError(EACCES)`, not a chmod of a file owned by the same account.

```
pytest -q --tb=line \
  client_tests/test_source_read_diagnostics.py \
  client_tests/test_connector_providers.py::test_folder_symlink_cannot_escape_selected_vault_or_certify_deletions \
  client_tests/test_connector_providers.py::test_file_replaced_after_checks_cannot_escape_selected_vault \
  service_tests/test_source_health.py::test_unreadable_selected_file_is_actionable_and_does_not_certify_deletion \
  service_tests/test_source_health.py::test_corrupt_file_keeps_other_updates_and_last_good_data_until_clean_scan \
  service_tests/test_source_health.py::test_health_explains_unavailable_sources_without_leaking_other_grants \
  service_tests/test_source_health.py::test_file_diagnostics_are_bounded_and_do_not_acknowledge_a_requested_sync \
  service_tests/test_source_health.py::test_unreadable_journal_catalog_still_closes_the_scope \
  service_tests/test_source_health.py::test_older_server_keeps_fail_closed_behavior_with_upgrade_hint \
  service_tests/test_source_health.py::test_git_pinned_inventory_isolates_content_errors_without_rewriting_sources \
  service_tests/test_source_health.py::test_partial_diagnostics_cannot_change_a_deletion_sweep_in_progress \
  service_tests/test_source_diagnostics.py::test_incomplete_inventory_diagnostics_omit_file_names_and_clear_after_repair \
  service_tests/test_source_diagnostics.py::test_resume_diagnosis_requires_fresh_provider_permissions_and_hides_raw_reasons
```

Result: 18 passed in 79.45s. The denial fixture names `denied.md` and `source_permission_denied`, omits the injected OS string and the host root, leaves `removed` and `changed` at 0, and keeps the earlier `completed_at`. After refresh, recall still contains the files indexed before the stop, omits the denied file and the file that came after it, and warns `connector_inventory_incomplete`. The unlinked file is not deleted. Reader health still omits the path.

`ruff check` and `ruff format --check` on the nine edited Python files passed. `json.load` of `docs/service/openapi.json` and `mnemion/service/agent_contract.json` succeeded. `info.version` is `4.46.53`.

Remaining, and not claimed here:

- No installed or live acceptance of 4.46.52, and no native matrix. V08 telemetry is untouched. The rest of issue 47 is untouched.
- There is no new SQL column. The failure is the latest run result with `incomplete_inventory` and `file_errors`. That run is still stored as completed. `last_successful` is false, as with existing content skips. Do not call the scan successful.
- A directory symlink found while walking still raises `source_symlinks_not_supported` and can be cleared by a later access refresh before a file receipt exists.
- A denied `.json` or `.jsonl` journal still becomes `journal_inventory_unreadable` without this `file_errors` receipt.
- Reader `health.sources` and administrator diagnostics JSON still omit paths. The operator sees the path on the scope inventory and in Studio File status.
- Sync control status stays the coarse `incomplete_inventory`. The category is on the scope result and in `file_errors`.
- The next scan's opening refresh can clear suspension, so embedding freshness can look current until that scan fails again. The previous incomplete warning remains.
- Before any incomplete receipt exists, the first failure can still look fresh until that scan finishes.
- These tests ran on WSL Linux. Windows may still follow an in-root symlink. A target outside the selected root is rejected by the handle check.
