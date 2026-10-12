# Password hashing foundation — 2026-10-12

**Post-4.1.2 source work, not an enabled sign-in feature.**

The existing pinned cryptography runtime provides Argon2id and PHC encoding.
The account foundation uses its implementation with 19 MiB, two iterations,
one lane, a fresh 16-byte salt and a 32-byte digest. This follows the
[OWASP Argon2id minimum profile](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html),
checked on 12 October. No package, paid service, account or certificate is added.

Nineteen local tests passed. They verify fresh salts, exact Unicode/space
preservation, input boundaries without truncation, rejection without echoing
passwords, unknown accounts and malformed or excessive PHC work parameters.
Only the reviewed cost profile can reach the library. Missing or invalid stored
verifiers use a dummy calculation whose result can never authenticate a person.

At most two hashes or verifications run concurrently per process; further work
gets the retryable `sign_in_busy` error. The concurrent test occupies both slots,
checks rejection of creation and verification, releases the workers and proves
failed attempts do not strand admission capacity. The configured 19 MiB is
algorithm memory per operation, not a guarantee about total process RSS or the
whole machine. Database/HTTP attempt throttling is still required before login
is exposed.

The local run used a 512 MiB / one-CPU process scope. Both Mac CI test jobs now
include the password suite, and each native build checks the selected service
runtime's real Argon2id support. Those remote checks are pending; they do not yet
prove a packaged password-login journey. Lint, formatting and workflow syntax
checks pass.

This module does not store accounts, issue sessions, reset passwords, enable
OAuth or alter existing API-key behavior. Continue with the
[individual sign-in contract](../implementation/individual-sign-in.md) before
advertising any of those workflows as available.
