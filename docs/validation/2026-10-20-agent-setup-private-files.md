# Private agent setup files

Validated on 20 October 2026 for source 4.30.2. Native release and public-update
results are recorded separately in [release status](../RELEASE_STATUS.md).

The setup helper previously created backups and temporary replacements using
POSIX mode flags. Those flags do not enforce a private Windows DACL, and the
copied configuration can contain credentials belonging to other providers.
Both files now use the existing exclusive private-output helper, which creates
Windows files with the current user as owner and a protected user-only DACL
before returning a writable handle. POSIX files retain mode 0600.

The exact prior configuration is backed up before a replacement is staged.
Concurrent edits still invalidate the preview, and publication remains an atomic
replace. Cleanup only removes the same staging object this operation created;
an exclusive-create failure does not authorize deleting an existing file.
Existing assistant policies, project trust, other servers and TOML comments
retain the earlier setup contract. JSON-only setup no longer imports the TOML
parser; TOML setup uses the same existing dependency when needed.

- **10 setup checks passed on Linux in 0.39 seconds**, including preserved Codex
  permission/trust settings, Unicode and Windows-style paths, other MCP servers,
  removal, invalid input, stale previews, exact backup retention after a failed
  replacement and preservation of an occupied staging path.
- **1 native Windows check passed in 0.56 seconds**. It inspected both files'
  actual owner and DACL before the first configuration bytes were written,
  verified the final files and exact original backup, and confirmed staging
  cleanup. It used a disposable synthetic configuration on the current PC.
- Formatting and focused lint checks passed. The new Windows case is part of
  the already required private-output suite on x64 and ARM runners, without a
  new database build input or dependency.

No actual assistant configuration was edited in this validation. This change
applies to new setup writes; it does not audit or rewrite older backups, change
an assistant's policy, or implement a new provider integration. Complete native
release gates remain required before publication. Strict full-scope roadmap
coverage remains 17/64.
