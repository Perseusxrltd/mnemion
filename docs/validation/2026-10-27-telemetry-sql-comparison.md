# SQL-read app comparison — 27 October 2026

Original [run 40523504727](https://github.com/Perseusxrltd/mnemion/actions/runs/40523504727)
completed successfully on its first attempt; retained qualification exited 0.
The measured source was `3034bc0b78b4b0ca52f2d794a3273a4e71999cca`, using workflow
source `e9fcc829a6dba7af2dc8c99efcc4f7aeef491373`. This was the unpackaged
Electron 44.9.3 / Node 24.22.0 app on Linux x64, with allocation attribution
disabled. It follows the [earlier Node source checks](2026-10-27-telemetry-sql-reads.md).

All six counterbalanced cases completed **128 memory cycles and 387/387
successful fixture API requests each**. Each matched **2,171 reviewed source
files**, with qualified app-process ownership, native setup controls and
cleanup. Each enabled case recorded 65 accepted telemetry writes, one
`[1, 65536]` attempt/byte reservation and one accepted four-byte report, with
zero forbidden metadata at the isolated collector. Its queue ended empty and
database size was 28,672 bytes. The other four cases recorded zero accepted
telemetry writes, reservations and deliveries. Leases cleared and isolated
profiles, certificates and collector were removed/stopped. The reservation is
an allowance, not a measurement of total network wire bytes.

**Resource acceptance remains false.** These are maximum matched-phase RSS
growth differences in bytes, each against its corresponding unavailable case;
they are not differences between independently observed peaks. CPU differences
are descriptive percentages of one core over the baseline window, rounded below.

| Case | App main | App renderer | GPU | Utility | CPU % |
| --- | ---: | ---: | ---: | ---: | ---: |
| r1 opted out | 942,080 | 815,104 | 81,920 | 102,400 | 0.108493 |
| r1 enabled | 2,572,288 | 7,036,928 | 5,263,360 | 131,072 | 0.397806 |
| r2 enabled | 2,859,008 | 0 | 446,464 | 0 | 0.210209 |
| r2 opted out | 1,961,984 | 0 | 217,088 | 65,536 | 0.000000 |

Both enabled main-process maxima exceed **2 MiB**; the first enabled renderer
and GPU comparisons also exceed it. Every recorded role/phase matched.
Zeros and cross-run variation establish no absent overhead or saving. RSS can
include shared pages, short-lived helpers can escape sampling, and these CPU
windows do not qualify the **0.5%** ceiling across representative work. Neither
the SQL change nor a particular allocation is established as the cause.

The retained qualification receipt SHA-256 is
`d3d8bd4f5f027ea7f2f6ed488178b41b8cd562b37377f614dc7ba21363287705`;
the original archive SHA-256 is
`c342c4ac5a457175ea9b7084542cb70cfa7230c71c6be7920d0d2680048197c5`.
`comparison-assessment.json` summarizes those original receipts without an app
rerun. The [previous comparisons and failures](2026-10-27-telemetry-acceptance-ledger.md)
remain unchanged. No installed/all-platform, whole-wire, provider/privacy or
full telemetry acceptance follows. All 66 requirements and V08 **Building**
remain; production collection/destination/route are **false/null/null**, with
empty release CAs and unchanged resource ceilings.
