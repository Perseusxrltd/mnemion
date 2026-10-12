# 4.1.1 publication and shared-workspace acceptance

Version **4.1.1** was published on **12 October 2026 at 10:12:28 UTC** for
Windows, macOS and Linux, each on x64 and ARM64. The
[release](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.1.1) is built from
`cd2b8fafe37a810b8b306fc9daf7cede1612f7bd`.

## Release verification

The [release run](https://github.com/Perseusxrltd/mnemion/actions/runs/38218651491)
passed the product checks and all six native installer, local-workspace and
update/relaunch gates. Three packaging/infrastructure failures were inspected
before retry: an Intel database source download failed DNS resolution; the
Apple Silicon packaging job encountered an invalid local database ZIP; and Intel
disk-image packaging encountered a busy mount. The stored Apple Silicon archive
was independently downloaded and its ZIP members verified before retry. The
final run passed on the same immutable source commit. Main separately adds
bounded retries for transient native source-download failures.

All **38 files, 3,863,815,399 bytes**, were downloaded and independently verified
against GitHub asset digests, the complete checksum inventory and embedded
production service/Windows/Mac public keys. Package versions, source and lock
identity, complete platform update feeds and bundled frontend inventories
agreed. The checksum-file SHA-256 is:

```text
edbf1a62454dbf96d5b9d40c1a118d4183e82f7018c73473d8b7566103dd9e08
```

The [post-publication check](2026-10-12-v411-publication.json) also confirms that
the public tag resolves to that exact source commit, 4.1.1 is the latest stable
release, and all 38 asset IDs, sizes and digests match the independently verified
draft. All public desktop/service feeds and the checksum file were fetched
without authentication and matched the verified bytes.

The separate [public-feed rehearsal](https://github.com/Perseusxrltd/mnemion/actions/runs/38234860579)
passed **4.1.0 → 4.1.1 automatic installation and relaunch on all six targets**.
It starts from unmodified previously published installers and exercises the
production feeds. The automatic [website metadata refresh](https://github.com/Perseusxrltd/mnemion/actions/runs/38234860544)
also passed and updated `main` without a manual website deployment.

At **10:42:05 UTC**, fresh desktop (1440 px) and mobile (390 px) browser checks
of the [live product page](https://www.perseusxr.com/mnemion) found all six
4.1.1 downloads, current release notes, documentation and the live roadmap.
The homepage links to the same product page and uses the same logo. The views
had no horizontal overflow or browser errors; both screenshots were inspected.
The [machine-readable website result](2026-10-12-v411-website.json) contains
only public URLs and observations. No website deployment was needed.

The [model cleanup validation](2026-10-12-model-idle-cleanup.md) records the
service/client/browser checks and real-model measurements. Idle-session release
does not combine the API and worker peak working sets, guarantee immediate RSS
reduction, or resolve every part of issue 13.

## Original shared host

At **10:24:01 UTC**, the original host completed the controlled
**4.0.14 → 4.1.0** schema migration. Before cutover, a fresh encrypted off-host
backup was verified locally and with the actual Windows recovery key. Windows
decrypted and hashed both files in memory at **10:23:38 UTC**, without writing a
plaintext backup or recovery identity. Ciphertext totalled **52,299,011 bytes**.

A one-shot operator job accepted a signed Windows receipt bound to this exact
backup. The existing 15-minute freshness requirement and reviewed migration
checks were retained. The job continued independently after launch, so a console
disconnect could not interrupt the verification handoff. This was a reviewed
operator migration, not an unattended schema upgrade or general host failover.

Only `014_author_withdrawal.sql` was applied. All **50 existing data tables**
retained their complete row hashes at migration; identities, keys and grants
were preserved. Reapplying migrations was a no-op. Authenticated API/MCP checks,
readiness, repeated idempotent startup, retirement of the old supervisor and
absence of owner database credentials in service children passed. The public
address stayed unchanged and no database backup was restored.

At **10:24:44 UTC**, Windows independently authenticated the saved human
administrator against service 4.1.0. The host then picked up **4.1.1** through
its enabled compatible patch channel. Windows authenticated the same human
administrator against 4.1.1 at **10:26:38 UTC**. No manual 4.1.1 check/stage/apply
command or polling-policy change was issued for this transition.

The [read-only host audit](2026-10-12-shared-host-v411.json), completed at
**10:54:30 UTC**, verified the active production signature, installed package
and dependency wheels, unchanged schema and embedding generations, and a
healthy supervisor with no recovery journal pending. Its recorded automatic
transition staged 4.1.1 at **10:25:31 UTC** and completed at **10:25:44 UTC**.
The six-hour polling preference remained unchanged.

The automatic pre-patch backup was independently verified: **52,279,409 bytes**,
two payload files, 51 table inventories (including schema migrations) and all
14 schema migrations. No database was restored. Running the normal host startup
entry point twice selected verified 4.1.1 and retained the same healthy service
processes. Owner database credentials were absent from API, worker and updater
environments. This verifies current idempotent startup; it does not claim a new
machine-reboot or disaster-recovery drill.

## Connected Windows lab

At **10:25:47 UTC**, the isolated lab identity was reduced from reviewer to
**contributor**, preserving its key, sole test-space grant and protected saved
profile. The human administrator and selected desktop connection were preserved.
No production memory was changed and no model call was made by that transition.

The bounded contributor cycle **passed at 10:38:33 UTC** on service 4.1.1:

| Observation | Result |
| --- | --- |
| Requests / elapsed time | 41 / 22.583 seconds |
| Client-observed p50 / p95 / maximum | 199.55 / 683.59 / 1651.96 ms |
| Peak client RSS / minimum observed free RAM | 44,974,080 / 828,698,624 bytes |
| Test data | Three synthetic memories, all deleted; no cleanup pending |
| Production writes / cloud-model calls | Zero / zero |

The run checked save idempotency, completed indexing, lexical and semantic
retrieval, persisted revision, stale-write rejection and author withdrawal.
It verified the active approved local CPU generation and kept contributor
authority for every memory operation. Eight of the 41 requests were narrowly
guarded, read-only identity/model-policy checks by the independent human
administrator. Expected permission denials and revision conflicts count as
successful assertions, not HTTP 2xx responses. The
[numerical result](2026-10-12-windows-contributor-4.1.1.json) excludes credentials,
private addresses, memory content and workspace identifiers.

Two earlier cycles exposed assumptions in the private test harness. The first
stopped after three requests when contributor access to reviewer-only model
choices was correctly denied; it wrote no memories. The second completed
29 requests and cleaned up its three synthetic memories, but an explicit
generation override was correctly denied as a reviewer-only preview operation.
The harness now obtains model-policy observations through its guarded human
administrator and uses ordinary active-generation recall as the contributor,
checking the returned generation and scope. Product permissions were not
weakened. The final cycle also explicitly confirms that the contributor cannot
inspect reviewer model choices.

This single-client, rate-limited synthetic cycle proves the stated operations
on the actual connection. It is not a concurrent server-capacity benchmark or
a representative retrieval-quality evaluation.

Built-in organization sign-in, invitations, delegated host operators, scheduled
off-host backups, guided recovery and peak-memory optimization remain on the
[complete requirements checklist](../PRODUCT_REQUIREMENTS.md).
