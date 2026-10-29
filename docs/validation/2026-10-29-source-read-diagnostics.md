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

Result: 18 passed in 79.45s. That run did not cover a file that had already been indexed and was then denied. The saved reproduction is `denial-refresh-failure.txt`: one failure in 44.90s. After a root refresh the reader could still recall `Postgres indexed before denial`. Those 18 passes are not evidence for the withhold below.

`ruff check` and `ruff format --check` on the nine edited Python files passed. `json.load` of `docs/service/openapi.json` and `mnemion/service/agent_contract.json` succeeded. `info.version` is `4.46.53`.

## Indexed denial, 29 October 2026

Migration `037_source_read_withhold.sql` adds nullable `connector_items.withheld_at` and `connector_items.validated_run`. It does not rewrite existing rows. `validated_run` is set only when a content observation is stored. A body-free retain updates `last_seen_run` only.

When the receipt contains an access-stop code, the same transaction sets `withheld_at` on every non-deleted item in that scope whose `validated_run` is not this run. That covers the named file and later files the walk never opened. A file read before the stop stays visible. The item is not marked deleted. Readable malformed files stay out of that set and keep the last good copy.

`read_scope` on `memories` and `memory_revisions` keeps the migration 035 predicate, `space_id IN (SELECT mnemion.authorized_spaces(10))`, and adds `NOT mnemion.source_memory_withheld(...)`. The function is `SECURITY DEFINER` so a reader can be filtered without a grant on `connector_items`. The connector principal is exempt, so the runner can repair. Worker, vault, capture, source, and embedding policies were not replaced. Reader source fetch still starts from `memories`, so the memory policy applies before the body is returned.

A later root refresh clears suspension only. It does not clear `withheld_at` or advance `completed_at`. The next scan can still begin, because refresh runs before `begin`. Repair restores the same memory ids when the bytes and revision are unchanged.

The first failure file was not run again. After the code change, the pinned interpreter ran:

```
pytest -q --tb=short \
  service_tests/test_source_health.py::test_previously_indexed_denial_stays_hidden_after_root_refresh \
  service_tests/test_source_health.py::test_unreadable_selected_file_is_actionable_and_does_not_certify_deletion \
  service_tests/test_source_health.py::test_corrupt_file_keeps_other_updates_and_last_good_data_until_clean_scan \
  client_tests/test_source_read_diagnostics.py \
  client_tests/test_connector_providers.py::test_folder_symlink_cannot_escape_selected_vault_or_certify_deletions \
  client_tests/test_connector_providers.py::test_file_replaced_after_checks_cannot_escape_selected_vault \
  service_tests/test_author_withdrawal_upgrade.py::test_previous_schema_upgrade_preserves_keys_grants_and_existing_memory[35]
```

Result: 13 passed in 83.16s. No skips. Python 3.12.3 in `/home/jorqu/.local/state/mnemion-release/2026-10-10/release-venv`. The log is `correction-checks.txt` beside the retained failure.

The indexed-denial test now uses `a-kept.md`, `m-denied.md`, and `z-second.md`. Both denied files were indexed, then both reads were denied. The receipt names only `m-denied.md`. After a root-only refresh, the reader still sees the re-read neighbor and a native memory in another granted space, and both denied memory ids return 404. `removed` stays 0. A retain of the denied item does not clear `withheld_at` or `validated_run`. Suspending that open run and refreshing again still hides both denied files. A later scan with the denial removed restores both bodies and the same ids, with `changed` 0 and `removed` 0. The never-indexed denial test still passes: the re-read neighbor stays, and the unvisited unlinked file stays hidden without being deleted. The corrupt-file cases still keep last-good text. The upgrade from migration count 35 preserves the inventoried rows; `connector_items` in that fixture is empty, so the new nullable columns do not change its hash. The other `previous_count` values were not repeated.

`ruff format` reformatted two files, then `ruff check` passed on `mnemion/source_codes.py`, `mnemion/connectors/source_files.py`, `mnemion/service/connector_models.py`, `mnemion/service/connectors.py`, `client_tests/test_source_read_diagnostics.py`, and `service_tests/test_source_health.py`. OpenAPI `info.version` remains `4.46.53`. No public contract field was added.

On Linux, `test_in_root_symlink_is_refused_and_ordinary_file_remains` passed. An in-root symlink and an outside redirect were refused, and the ordinary file was read. That interpreter is not Windows. The native Windows run is recorded below.

## Inference hold and Windows, 29 October 2026

Migration `038_embedding_withhold.sql` adds `embedding_revision_current(revision)`. It does not rewrite rows and does not change `embedding_source_current`. The worker calls it from the same policy that already runs before inference and before publishing vectors. A withheld revision is put back to `pending` with `source_access_unavailable` and is not sent to the embedder. A neighboring item that this scan re-read stays eligible. Reindex backfill still enqueues a held revision, then delays that job for 60 seconds; the worker checks again before any model call. The connector principal is not exempt from this function.

The earlier 13 passes were not repeated. The pinned Linux interpreter ran only the new regression and the migration-count 35 upgrade:

```
pytest -q --tb=short \
  service_tests/test_source_health.py::test_withheld_source_is_not_embedded_after_root_refresh \
  service_tests/test_author_withdrawal_upgrade.py::test_previous_schema_upgrade_preserves_keys_grants_and_existing_memory[35]
```

Result: 2 passed in 61.59s. Python 3.12.3. The log is `embedding-withhold-checks.txt`. After a root refresh, the fake embedder was not called for `Postgres indexed before denial` or `Postgres second denial unread`, and neither memory had an embedding. The re-read neighbor was embedded. After the denial was removed, the same unchanged bodies were embedded. The upgrade from count 35 still preserved inventoried rows.

Denial fixtures no longer patch only POSIX `os.open`. On Windows they patch `_windows_open_unfollowed`. The replaced-file race does the same. `astra-native-windows-checks-20261029.txt` remains the earlier collection failure: system Python 3.13 had no `pydantic`, so no test ran. That is an environment limit, not a runtime failure.

The native re-run used an isolated venv at `%TEMP%\field47-win-pytest`, Python 3.13.11 (MSC v.1944 64 bit), with only `pydantic==2.14.0`, `pytest==9.1.1`, `httpx==0.28.1`, and `defusedxml==0.7.1`. No embedding or model package was installed. No global interpreter was changed.

```
pytest -q --tb=short \
  client_tests/test_source_read_diagnostics.py \
  client_tests/test_connector_providers.py::test_folder_symlink_cannot_escape_selected_vault_or_certify_deletions \
  client_tests/test_connector_providers.py::test_file_replaced_after_checks_cannot_escape_selected_vault
```

Result: 8 passed in 1.32s. No skips. The log is `windows-native-checks.txt`. On this account the checks that ran were: a regular file read, a missing file, an injected denial through the Windows opener, an in-root symlink, an outside redirect, a directory symlink refusal, a file replaced with an outside symlink before `CreateFileW`, and 20 failed `open_osfhandle` conversions whose process handle count did not grow. Symlink creation succeeded here, so the privilege skip did not trigger. This is not a second Windows account and not an installed service.

`ruff format` and `ruff check` passed for `mnemion/service/worker.py`, `mnemion/service/reindex.py`, `service_tests/test_source_health.py`, `client_tests/test_source_read_diagnostics.py`, and `client_tests/test_connector_providers.py`. OpenAPI `info.version` remains `4.46.53`.

Remaining, and not claimed here:

- No installed or live acceptance of 4.46.52, and no native matrix. V08 telemetry is untouched. The rest of issue 47 is untouched. This is not a release.
- The failure remains the latest run result with `incomplete_inventory` and `file_errors`. That run is still stored as completed. `last_successful` is false. Do not call the scan successful.
- A directory symlink found while walking still raises `source_symlinks_not_supported` and can be cleared by a later access refresh before a file receipt exists.
- A denied `.json` or `.jsonl` journal still becomes `journal_inventory_unreadable` without this `file_errors` receipt.
- Reader `health.sources` and administrator diagnostics JSON still omit paths. The operator sees the path on the scope inventory and in Studio File status.
- Sync control status stays the coarse `incomplete_inventory`. The category is on the scope result and in `file_errors`.
- App `read_scope` on `embeddings`, `sources`, and `source_revisions` was not given the per-file predicate. Reader recall, fetch, history, and source fetch go through `memories` first. The worker role can still read withheld rows; `embedding_revision_current` is what stops a new embedding. Vectors written before the hold are not deleted.
- The next scan's opening refresh can clear suspension, so embedding freshness can look current until that scan fails again. The previous incomplete warning remains.
- Before any incomplete receipt exists, the first failure can still look fresh until that scan finishes.
