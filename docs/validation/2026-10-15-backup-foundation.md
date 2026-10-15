# Encrypted backup foundation

This is **unreleased source work** toward the
[native backup/recovery contract](../implementation/native-backup-recovery.md),
following the 4.4.0 remote-access batch. This record covers the foundation.
The follow-on [desktop workflow](../service/native-backups.md) now implements
scheduling, protected keys and native restoration in source; native release
acceptance remains in progress.

The portable envelope uses streaming AES-256-GCM with random 256-bit recovery
keys and 96-bit nonces. It authenticates the complete versioned header and
payload, rejects unknown/duplicate/oversized fields and requires the exact
declared file length. A key fingerprint is a lookup hint, not authentication.
Human passwords and ambiguous key encodings are refused. The existing 50 GiB
archive limit remains; each I/O block is bounded to 1 MiB.

Encryption publishes only ciphertext. Verification reads all encrypted bytes
without retaining plaintext; decryption publishes a private file only after the
GCM tag and source-file identity checks pass. Cancellation and failures remove
only this operation's staging file. The desktop workflow keeps its exported key
outside the backup folder and uses the native protected store for scheduling.

Archive publication now falls back from hard links to an exclusive native
rename: Windows rename, macOS `renamex_np(RENAME_EXCL)`, or Linux
`renameat2(RENAME_NOREPLACE)`. Unsupported atomic publication fails without an
overwriting fallback. Ciphertext staging does not require a shared/removable
filesystem to enforce private-file permissions; plaintext staging still does.

The first Linux run passed **29 encryption/publication tests**, covering empty
and multi-block payloads, comparison with the one-shot AESGCM API, changed
headers/body/tags, a wrong key or payload type, truncation/appending, cancellation,
source changes, bounded reads, duplicate/oversized headers, links/devices,
existing outputs, and concurrent publication with and without hard links.
The final run passed **31 tests**, including staging-collision checks that
protect unrelated pre-existing files. Lint and formatting also passed. These
are functional regression checks, not an independent cryptographic audit or
measurements of a real cloud filesystem. Native platform coverage, complete
PostgreSQL recovery and the app workflow retain their own acceptance gates.

No actual workspace data, cloud storage account or production credentials were
used. This work does not close A04, A06, A09, U01 or U02 by itself.
