# Legacy managed-model custody — 27 October 2026

Source follow-up based on `e7cdd91d089a3a68cebed22b076a32fbe5a10c0d`, scoped to
the classic CLI and legacy backend. The original selection retained **12 failed
regression cases**: broad process-name shutdown, interpolated/rewritten WSL
launches, false-success model tests, restart after unverified shutdown and
idle control of an external endpoint. These results do not show that a user's
model or unrelated live process was stopped.

The new [process controller](../../mnemion/managed_model_process.py) keeps
private PID and process-birth identity records, including Linux boot/start
identity, under a lock with atomic publication. Native shutdown selects the
recorded process and currently verified descendants; names and endpoint
reachability grant no ownership. Cross-process request leases defer automatic
idle/restart teardown, and launch generations prevent old leases or watchers
from controlling a replacement. Manual stopping may cancel active requests.
Verified shutdown retains a private terminal stopped receipt for idempotent
repeat stops. Automatic restart holds stop/relaunch under one lock, defers for
active leases, refuses a still-reachable endpoint and cannot override that
explicit stopped state. Controller keys include resolved launch arguments so
different working-directory-relative scripts do not share custody.
Foreground scripts remain required; this is not custody of detached daemons
or a persistent supervisor installed by a short CLI invocation.

The [backend](../../mnemion/llm_backend.py) launches native Windows `.ps1` and
`.exe` paths as arguments. WSL scripts are passed unchanged with explicit
distribution selection. A recorded Windows launcher cannot establish guest
ownership, so guest stop/restart/idle teardown refuses; the original guest
manager is still required. Durable guest custody and all-platform acceptance
remain unfinished.

The [CLI](../../mnemion/cli.py) now accepts only an exact trimmed `MNEMION_OK`
reply as a successful model test. Failed tests/startup or an endpoint still
reachable after recorded shutdown return exit **1**; disabled testing/startup,
unsupported startup and absent/unverified shutdown custody return **2**.
`llm stop` attempts native custody even when the endpoint is unreachable;
reachability no longer bypasses process control. No managed backend remains an
exit **0** no-op; verified initial/repeat stops return **0** when the endpoint
is unreachable. The [management guide](../guides/llm-backend-management.md)
describes these distinctions; Studio provider settings are outside this change.

**Final source qualification passed 128 distinct tests in 12.64 seconds**, with
no failures or skips; Ruff passed. This includes 17 real
[native lifecycle cases](../../native_tests/test_managed_model_process.py),
[backend/CLI checks](../../tests/test_managed_model_control.py), existing classic
CLI/coverage checks and process-identity checks. The lifecycle fixtures use
disposable synthetic children; model replies are fake. The release platform
matrix remains pending, with no real model/provider calls, source-app journey
or live-service change qualified.

The original 12 failures and preliminary 27-pass stage remain retained.
`final-python.log` also retains 127 passes and one stale classic CLI expectation:
disabled `llm start` now correctly exits 2. That test was corrected while
preserving its unconfirmed telemetry outcome. `final-python-corrected.log` and
`final-python.xml` record the final 128 passes; overlapping stages are not added.

All **545 tested runtime/test inputs** matched after the final checks. The
`runtime-inputs-final.json` manifest digest is
`ff470b868ac178fa821104439264ebc066b02a063c7a0492a4422c5fa2e81f79`.
Version preparation produced a 545-file release input digest of
`8e89ffd60a785d9ac3a1aac208564a5aaf78dba7fd49e138bcce12a7a0f02738`;
only four selected metadata files changed by exact 4.46.39-to-4.46.40 version
replacements. Runtime code remained unchanged; preparation does not qualify
the release platform matrix or establish publication.
No runtime dependency was added. Already-locked pytest 9.1.1 was added to the
native-build group only; the offline lock refresh changed no package versions
and installed nothing.

Telemetry remains unavailable: collection/destination/route are
**false/null/null**, with empty release CAs. All 66 requirements and **V08
Building** remain unchanged. The existing 94 mapped categories do not close
the two unmeasured classic paths, `split` and `llm test`; proposed
`capture.split` and `models.test` extensions remain separate work requiring
compatible catalog and historical-report handling. Existing resource,
wire/privacy/provider, installed and release gates remain open, with no new
resource comparison or measured savings.
