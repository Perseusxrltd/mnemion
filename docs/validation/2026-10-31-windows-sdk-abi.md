# Windows SDK structure layouts — 31 October 2026

The standalone SDK measurement passed on native x64 and ARM64 in [run 41237380248](https://github.com/Perseusxrltd/mnemion/actions/runs/41237380248), on exact source `781bef2e83532342a3bbcad99810e12875b2e046`. Both targets used Windows SDK **10.0.26100.0**. Their original `abi.json` files are **2,824 bytes each**, with identical numeric layouts except the architecture identifier.

| Native target / runner | Observed OS build | MSVC compiler | Original artifacts |
| --- | --- | --- | --- |
| x64 / `windows-2022` | Server 2022, `20348.5761` (`21H2`) | `19.44.35229` for x64 | [ABI JSON](2026-10-31-windows-sdk-abi-x64-abi.json), [metadata](2026-10-31-windows-sdk-abi-x64-metadata.json) |
| ARM64 / `windows-11-arm` | `26200.9711` (`25H2`) | `19.51.36260` for ARM64 | [ABI JSON](2026-10-31-windows-sdk-abi-arm64-abi.json), [metadata](2026-10-31-windows-sdk-abi-arm64-metadata.json) |

The four artifacts are retained verbatim. ARM64's registry `ProductName` reports `Windows 10 Enterprise`; its actual runner is `windows-11-arm`, with the build/version shown above. The metadata preserves that registry value.

The C program measured SDK `sizeof`/`offsetof` values, including both unions and callback fields. On both targets, `WNODE_HEADER` is 48 bytes, `EVENT_TRACE_PROPERTIES` 120, `EVENT_HEADER` 80, `EVENT_RECORD` 112 and `EVENT_TRACE_LOGFILEW` 448. `EVENT_RECORD.UserContext` is at offset 104; the logfile's buffer callback, event-record callback and context are at offsets 400, 424 and 440. The JSON contains the complete primitive widths, structure sizes and member offsets.

Earlier original runs remain part of the record: [41235704364](https://github.com/Perseusxrltd/mnemion/actions/runs/41235704364) failed during compiler-banner handling, and [41236393348](https://github.com/Perseusxrltd/mnemion/actions/runs/41236393348) failed while parsing case-distinct JSON keys such as `size_t` and `SIZE_T`. One direct parser check also passed. The successful run does not replace those original outcomes.

This validates the standalone SDK measurement and its numeric receipts. The run did not load the Python ETW provider or execute tracing/profile operations. Comparison with a ctypes/FFI implementation, ETW emission and lifetime accounting, and actual application CPU/RAM budget qualification remain separate work. Production collection stays off; telemetry acceptance and all 66 requirement states are unchanged.
