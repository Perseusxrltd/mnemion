# Windows SDK structure layouts — 31 October 2026

The standalone SDK measurement passed on native x64 and ARM64 in [run 41237380248](https://github.com/Perseusxrltd/mnemion/actions/runs/41237380248), on exact source `781bef2e83532342a3bbcad99810e12875b2e046`. Both targets used Windows SDK **10.0.26100.0**. Their original `abi.json` files are **2,824 bytes each**, with identical numeric layouts except the architecture identifier.

| Native target / runner | Observed OS build | MSVC compiler | Original artifacts |
| --- | --- | --- | --- |
| x64 / `windows-2022` | Server 2022, `20348.5761` (`21H2`) | `19.44.35229` for x64 | [ABI JSON](2026-10-31-windows-sdk-abi-x64-abi.json), [metadata](2026-10-31-windows-sdk-abi-x64-metadata.json) |
| ARM64 / `windows-11-arm` | `26200.9711` (`25H2`) | `19.51.36260` for ARM64 | [ABI JSON](2026-10-31-windows-sdk-abi-arm64-abi.json), [metadata](2026-10-31-windows-sdk-abi-arm64-metadata.json) |

The four artifacts are retained verbatim. ARM64's registry `ProductName` reports `Windows 10 Enterprise`; its actual runner is `windows-11-arm`, with the build/version shown above. The metadata preserves that registry value.

The C program measured SDK `sizeof`/`offsetof` values, including both unions and callback fields. On both targets, `WNODE_HEADER` is 48 bytes, `EVENT_TRACE_PROPERTIES` 120, `EVENT_HEADER` 80, `EVENT_RECORD` 112 and `EVENT_TRACE_LOGFILEW` 448. `EVENT_RECORD.UserContext` is at offset 104; the logfile's buffer callback, event-record callback and context are at offsets 400, 424 and 440. The JSON contains the complete primitive widths, structure sizes and member offsets.

Earlier original runs remain part of the record: [41235704364](https://github.com/Perseusxrltd/mnemion/actions/runs/41235704364) failed during compiler-banner handling, and [41236393348](https://github.com/Perseusxrltd/mnemion/actions/runs/41236393348) failed while parsing case-distinct JSON keys such as `size_t` and `SIZE_T`. One direct parser check also passed. The successful run does not replace those original outcomes.

The expanded [run 41244785682](https://github.com/Perseusxrltd/mnemion/actions/runs/41244785682) passed on both native targets at source `f49ab34923d018efb3d2d30beb3a954aa6b73a48`, using the same SDK. Its original ABI JSON files are **3,466 bytes each**. The original nine structure records are unchanged; the five added records—`GUID`, `SYSTEMTIME`, `TIME_ZONE_INFORMATION`, `ETW_BUFFER_CONTEXT` and `EVENT_HEADER_EXTENDED_DATA_ITEM`—also agree across targets. Both original archive hashes and their exact two-file contents were reviewed. The expanded files are retained separately and verbatim: [x64 ABI](2026-10-31-windows-sdk-abi-expanded-x64-abi.json), [x64 metadata](2026-10-31-windows-sdk-abi-expanded-x64-metadata.json), [ARM64 ABI](2026-10-31-windows-sdk-abi-expanded-arm64-abi.json) and [ARM64 metadata](2026-10-31-windows-sdk-abi-expanded-arm64-metadata.json).

The extended item has a 16-byte size/array stride, with `ExtType` at byte offset 2. The SDK byte experiment locates the combined `Linkage`/`Reserved2` storage at offset 4, spanning 2 bytes, with masks 1 and 65,534. These are measurements of the SDK layout and bitfields; they are not a Python/provider bitfield-value comparison. Earlier expansion runs [41243254134](https://github.com/Perseusxrltd/mnemion/actions/runs/41243254134) and [41243958689](https://github.com/Perseusxrltd/mnemion/actions/runs/41243958689) failed with compiler diagnostics `C4244` and `C4310`, respectively. Those original failures remain recorded.

The first native ctypes declaration comparison passed on x64 and ARM64 in [run 41248868407](https://github.com/Perseusxrltd/mnemion/actions/runs/41248868407), at exact source `7a7ee629e9be09f91aad79b311c885372a6993fb`, using native Python **3.13.17**. Each receipt reports `declaration_match=true`, all **14 structure sizes**, **137/137 addressable field matches**, 18 primitive-width comparisons, and no missing layouts, mismatches or omitted mismatches. The executed provider SHA-256 is `7bf10ca9ec44b3f121e5dbc7fc9e403f240dbb010a166004fdbeb9b5fe2c6b32`; its oracle is the expanded SDK run above.

| Native target | Original declaration receipt | Bytes |
| --- | --- | --- |
| x64 / `windows-2022` | [Verbatim JSON](2026-10-31-windows-etw-declaration-x64.json) | 47,287 |
| ARM64 / `windows-11-arm` | [Verbatim JSON](2026-10-31-windows-etw-declaration-arm64.json) | 47,291 |

Each original archive contains exactly one `declaration-receipt.json`; both archive hashes match the published digests, and strict JSON review found no duplicate keys. The numeric results are identical across targets. The provider's opaque `Linkage` USHORT matches the measured storage span; the masks and 17 SDK-only union aliases remain separate from the 137 declared-field matches. The comparison records zero additional provider library loads and `native_api_loaded=false`. CPython's initial ctypes import itself binds `kernel32.GetLastError`.

The SDK runs measured C layouts; the later comparison loaded reviewed Python declarations. Neither started an ETW trace. The receipts keep native tracing, emission, production readiness and CPU/RAM/resource acceptance false. ETW emission, owned cleanup, lifetime/counter correctness and actual application resource budgets remain separate work. At this milestone, the public release remained **4.46.62**; telemetry acceptance and all 66 requirement states were unchanged; **V08 remains Building with collection OFF**.
