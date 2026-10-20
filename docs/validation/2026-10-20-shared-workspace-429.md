# Shared workspace and actual Windows update to 4.29

Recorded 20 October 2026. Private addresses, account identifiers, credentials
and memory contents remain outside this repository.

The published **4.29.0** source was verified before applying its official guarded
server upgrade. A fresh encrypted 4.28 snapshot and latest access ledger had
already reached independent Git storage; an authenticated GitHub manifest read
confirmed their identities, hashes and lengths. The upgrade plan contained only
`028_journal_uploads.sql` and matched the verified release commit.

The host completed the guarded upgrade from 01:14:27 to 01:16:06 UTC. Backup
timers were paused while existing jobs drained, then restored after readiness.
The managed recovery journal was clear, API/worker readiness passed and compatible
automatic updates remained enabled. No old database was restored in place.

Fifteen external read-only checks preserved the owner and both agent identities,
their exact space roles, the two recorded memory revisions and content hashes,
an existing permanent deletion, personal login configuration and MCP/OAuth
discovery. The same shared organization remained selected.

The actual Windows x64 installation downloaded and installed **4.28 → 4.29**
through its normal update channel after an ordinary check request. It relaunched
without a manual installer or forced restart. Automatic updates, login startup,
background operation, the protected personal login and both existing bookmarks
were retained. Its separate restricted reliability lab then passed one automatic
cycle for the **4.29 app / 4.29 server** pair, with no pending synthetic cleanup.
No concurrency burst or paid model call was needed.

The previously empty administrator recovery directory now records the real
primary host, the cold recovery PC, independent operator access, database/ledger
locations and a separately labeled source mirror. Both ordinary agent keys were
denied access to these administrative references. The actual Windows app refreshed
its existing personal bookmark and read back the same revision from protected
offline storage without a network request. Registration does not make the PC a
replica or delegate provider authority.

A new **4.29** encrypted full package and later ledger were independently
confirmed off-host at 01:22 UTC after the migration and directory enrollment.
The new package measured 88,626,039 bytes. The directory's dated verification
fields remain explicit earlier administrator observations; they are not automatic
provider health checks.

All six public installed-update checks for 4.29 subsequently passed. Source,
release and public upgrade receipts are in [automatic release status](../RELEASE_STATUS.md).
The original office database/vault remain unavailable. Signed-in ChatGPT and a
live managed tunnel account were not tested by this exercise. The
[current issue plan](../implementation/github-issues.md) separates those remaining
checks from completed general OAuth and remote-access reports.
This exercise does not establish automatic failover,
independent second-device key custody or universal hardware capacity.
