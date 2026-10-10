# Shared memory and scheduled Obsidian refresh

Applications and assistants now share the authenticated Mnemion service. Each
client has its own credential and explicit space grants. Saves, corrections,
reviews, and deletions use the same authoritative database.

`SyncMemories.sh` and `SyncMemories.ps1` now refresh a local Obsidian vault through
that service. They use the same verified export/refresh path as Studio and the
Python client, preserving personal sections, stable note paths, and conflicts.
They perform no Git operations.

## Configure a vault

Create a private credentials JSON file containing `api_key` and `api_url`. Use a
reader key granted only the spaces this vault should contain. A reviewer export
requires a reviewer key and an explicit `"review": true` configuration.

Create `obsidian-refresh.json`:

```json
{
  "credentials_file": "/private/mnemion-reader.json",
  "vault_path": "/notes/Mnemion",
  "space_ids": ["YOUR_SPACE_UUID"],
  "review": false
}
```

Use absolute paths appropriate for the local operating system. Register the
vault in Obsidian once, then refresh it:

```sh
python -m mnemion.vault_sync --config /private/obsidian-refresh.json --dry-run
python -m mnemion.vault_sync --config /private/obsidian-refresh.json
```

A conflict leaves the last completed watermark unchanged and returns exit code 2.
Review the proposed changes before running the next refresh. Obsidian is an
inspectable local projection: withdrawn content is removed from managed sections
on refresh; personal annotations remain the user's files.

## Optional scheduling

On Linux, set `MNEMION_VAULT_CONFIG` to the configuration file and call
`sync/SyncMemories.sh` from the chosen scheduler. `MNEMION_PYTHON` can select the
installed environment's Python executable. Schedule one job per vault; refreshes
use a local lock.

On Windows, install Mnemion's Python package, then review the task configuration:

```powershell
powershell -NoProfile -File sync\install_windows.ps1 `
  -CredentialsFile C:\Private\mnemion-reader.json `
  -VaultPath C:\Notes\Mnemion `
  -SpaceIds YOUR_SPACE_UUID `
  -PythonExe C:\Mnemion\.venv\Scripts\python.exe `
  -DryRun
```

Run the same command without `-DryRun` to write the configuration and register
`MnemionObsidianRefresh` for the current user. `-SkipSync` writes the configuration
without registering a task. `-MnemionDir`, `-SyncTaskName`, and
`-SyncIntervalHours` customize its location, name, and interval. Existing
configuration files are not overwritten. Assistant hooks and model-server startup
are configured separately by the applications that need them.

## Migration from Git sync

The v3 array-union merge and optional SQL-dump merge are retired. They could
resurrect deletions, reset trust state, and expose an entire personal corpus to
any participant with repository access. A Git export was not a complete backup.
The old merge command now fails before writing output, and an old scheduled sync
without a service configuration fails before touching the profile.

Stop the old cron/Task Scheduler job. Preserve and verify the installation with
[the complete v3 backup and restore commands](../docs/service/recovery.md), then
migrate it into an explicitly owned private space. Configure each assistant or
application to use the service and each Obsidian vault to use an authorized
refresh credential. Git repository history still contains its earlier exports;
retention of those copies is an operator decision, independent of service deletion.

The original scripts and documentation are retained as non-executable historical
text under [docs/legacy](../docs/legacy/). They are not supported replication paths.
