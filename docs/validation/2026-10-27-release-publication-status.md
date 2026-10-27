# Release publication status — 27 October 2026

The original [v4.46.39 native run](https://github.com/Perseusxrltd/mnemion/actions/runs/40504681891)
succeeded. In [verification run 40512666290](https://github.com/Perseusxrltd/mnemion/actions/runs/40512666290),
attempt 1's uploaded-byte verification job **122218239802** passed, but
publication job **122220779406** failed before any publication mutation with
`The uploaded-byte verification job must have passed`.

The original job-status API response was not retained. Delayed metadata is a
plausible timing explanation, not a proven cause. The original failed attempt,
draft observation and failure log remain retained; the log SHA-256 is
`5c7984ea993e4fa1b4b5db61e0b284eec57f6ab8de6d24a56d92a4551f5b7e21`.
After inspecting that evidence, only the failed publication job was resumed
once. Attempt 2 succeeded and [v4.46.39 became public](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.39)
at **2026-10-27T14:26:59Z**, confirmed by a live GitHub read. The successful
byte-verification job was retained; there was no native rebuild or byte rescan.
The earlier resume-request receipt records acceptance before publication and
does not itself establish the later public result.

The new [publisher guard](../../deploy/release_automation.py) requires exactly
one successful completed verification job. `wait_for_verified_bytes` polls
read-only job metadata within a 60-second polling window when the verifier is
missing, queued or in progress. Failed, skipped, ambiguous or otherwise
terminally invalid evidence is refused immediately; API errors are not retried.
This wait performs no publication mutation or automatic publication retry.
Existing receipt, inventory, signature and trusted-source checks remain.

All **38 focused publisher tests passed in 1.40 seconds**, with no failures or
skips; Ruff passed. [Tests](../../service_tests/test_release_automation.py),
`publisher-tests.log`/`.xml` and `publisher-checks.json` retain that source
qualification. It is separate from the successful resume of the older frozen
release and does not prove the original timing cause.

Together with the unchanged [SQL-read source group](2026-10-27-telemetry-sql-reads.md),
this batch has **161 distinct passes and two Windows-only skips**. The 123
native-source passes ran under Node 22.22 on Linux x64 and were not rerun;
they are not an actual Electron app journey. No resource saving or installed
platform qualification follows. Production telemetry stays disabled, all 66
requirements and V08 Building remain unchanged, and the resource/privacy/full
acceptance gates remain open.
