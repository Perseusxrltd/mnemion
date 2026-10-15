# Recovery directory, protected copies and independent kit

This report covers the source batch prepared for **4.8.0**. Publication and native
installation/update results remain separate in [release status](../RELEASE_STATUS.md).
The development browser walkthrough ran before the package version was advanced.

## Service, isolation and real restoration

The focused service/directory/kit/recovery selection passed **24 tests** against
a disposable PostgreSQL 18.6 database with pgvector. A separate administrator,
without a memory-space grant, created and read the directory after the original
administrator was disabled. A restricted assistant received HTTP 403, another
tenant retained its own directory, and the worker login could not select the table.

Concurrent edits produced one accepted revision and one HTTP 409. The audit event
contained revision and entry counts, not free-text host or contact references.
Directory text did not enter lexical memory retrieval. Invalid URLs, obvious
credentials, control characters, blank required references, excessive Unicode
data, future verification reports and duplicate entry IDs were rejected.

The existing complete backup/restore exercise now includes a configured directory.
A real snapshot and current access/deletion ledger restored it with the original
revision and editor history. Old keys remained rejected. The new recovery
administrator could update it to the next revision while the exercise continued
to verify memory deletion, access revocation and queued-work reconciliation.

## Desktop persistence

**50 desktop store, connection and personal-sign-in checks passed.** New cases
cover encrypted recovery metadata across process/store recreation, locked storage,
another tenant or destination, credential reflection, corrupt optional metadata,
large optional records, current loss of administrator authority, an unavailable
directory service, explicit access denial, and a late refresh after disconnect.
Inspection leaves the workspace disconnected and makes no server request.

These focused tests use a disposable authenticated cipher. Actual native
keychain/DPAPI acceptance is required by the ordinary release jobs. The installed
workspace probe now captures and refreshes administrator recovery references,
checks they are absent from the plaintext bookmark file, restarts the app with
the directory endpoint unavailable, and requires the protected copy to remain
readable. The old outer bookmark format and per-record size boundary are retained.

## Browser, CLI and offline interoperability

A Playwright CLI walkthrough used the actual service and built Studio with a
separately created administrator and no memory-space grant. It saved a host,
independent entry URL, a source-mirror location and an independent contact through
the form. Unsaved edits protected desktop updates; successful save cleared that
state. Desktop and 390-pixel mobile captures were visually reviewed, with no
horizontal overflow.

The app downloaded an encrypted kit and cleared its passphrase fields. Python
decrypted that browser-generated file and verified the record against an actual
`mnemion-control ... call recovery.directory --result-file ...` response. After
the fixture service was stopped, the installed CLI entry point generated a kit
from that private result file without contacting the host.

With the browser network disabled and the service stopped, the browser-generated
kit opened from a local file. A wrong passphrase was rejected; the correct one
showed the recorded host and the explicit **source mirror · tracked documents
only** scope. Script-like text remained literal, provider links isolated their
opener, locking cleared displayed metadata, and the complete viewing cycle made
**zero HTTP requests**. The CLI-generated kit also opened in the browser offline.
No provider console or real recovery storage was contacted.

Kit tests cover authenticated ciphertext, a changed authentication tag, incorrect
passwords, removal of unknown response fields, the inline CSP hash, bounded
inputs, private output, and refusal to overwrite an existing kit. A final focused
kit run covers the control CLI's private result envelope and escaped Unicode near
the directory limit. The shared generated viewer includes the canonical logo
and the same validator as the desktop; desktop builds check its consistency.

## Scope still open

This evidence does not establish live cloud backup delivery, independent host
authority/delegation, company identity-provider setup, recovery-custodian policy,
replication or safe takeover. A referenced source mirror is not a complete
database backup. Existing cached or exported copies cannot be remotely revoked;
the receiving organization must control their delivery and passphrase handling.
The [full requirements](../PRODUCT_REQUIREMENTS.md) remain **17/64 shipped**;
this batch advances several partial continuity requirements.
