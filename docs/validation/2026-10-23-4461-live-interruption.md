# 4.46.1 live rollout: interruptions and reviewed acceptance

**23 October 2026.** The actual Windows/shared-host pair completed
[4.46.1 acceptance at 09:55:28 UTC](2026-10-23-4461-live-acceptance.md).
This history preserves the two stopped attempts and their inspection before
that accepted result. The six-platform
[native and public qualification](2026-10-23-4461-native-acceptance.md) and
the separate [4.46.0 rollback](2026-10-23-4460-live-rollout.md) remain recorded.

## Interrupted pre-update backup

The host staged 4.46.1 at **08:41:22 UTC**. Its pre-update backup was still
running at **08:54:36 UTC**, with 4.45.1 active. The installed OS watchdog
requested service restarts at **08:56:52 and 08:58:19 UTC**, recording
`ready: false`, `restart_requested: true`, `maintenance: false` and
`managed_recovery_pending: false`.

The watchdog's recovery guard recognized `journal.json` or
`upgrade-journal.json`, which the updater writes after the backup. Neither
existed for this attempt, so the guard did not cover the running backup.
The inspected backup log was empty and no backup process remained afterward.
The observer stopped at **09:00:54 UTC** with Windows 4.46.1 and host 4.45.1;
dependent backup/adoption jobs stopped at their prerequisites without retry
or downstream actions.

The candidate had not activated or reached its runtime-readiness boundary.
The retained failure marker still described the **4.46.0 rollback at 06:14:47
UTC**, not a new 4.46.1 rollback. The installed watchdog source was retained
with SHA-256
`78b4b6f71fb7342933a40c399043902f41b0ffa0b280c2a4fb354470f1eef1d5`.

## Completed update and stopped access comparison

A separately recorded continuation used the existing OS maintenance guard.
The normal updater completed its **1,125-second backup** and recorded the
compatible update to 4.46.1 at **09:38:36 UTC**, with full readiness and no
recovery pending. Windows retained its earlier guarded update.

At **09:39:20 UTC**, external acceptance stopped with **“Previously accessible
space was lost”**. The failure did not record which exact space was missing.
Read-only comparison at **09:45 UTC** found all baseline spaces, roles and
three identities retained. Two Git source spaces were additionally visible
to both agent identities; the complete identities and space/role maps matched
the accepted [00:31 UTC 4.45.1 configuration](2026-10-23-4451-live-acceptance.md).

Provider access leases last **900 seconds**. Audit evidence captured at
**09:48:15 UTC** showed a renewal gap during backup/restart, followed by renewed
checks around **09:39–09:42 UTC**, with no grant or principal mutation in the
inspected interval since 09:10 UTC. This supports the reviewed visibility
restoration without establishing the exact missing-space failure attribution.
The owned maintenance marker was released at **09:45:42 UTC** after full
readiness, without restarting the service or reapplying the update.

Independent review matched the **four restored source-role entries** against
both prior accepted authority and current provider bindings. Missing original
spaces and unreviewed changes remain rejected; the review granted no access.
The final paired acceptance passed with the existing 54-request lab receipt,
complete cleanup, zero production memory writes and zero cloud model calls.
Both original stopped receipts remain preserved.

The paired update is accepted. Fresh independent backup verification,
OS/controller adoption and both custodians' operations remain pending; all
[66 requirement texts and states](../PRODUCT_REQUIREMENTS.md) are unchanged.
[V08 telemetry](../implementation/anonymous-product-telemetry.md) remains
Planned and inactive.
