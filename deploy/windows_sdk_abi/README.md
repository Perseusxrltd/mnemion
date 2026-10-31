# Windows SDK ABI oracle

This directory measures structure layout. It is not native tracing, and a run here is not resource acceptance.

`sdk_abi.c` includes the Windows SDK headers and prints one bounded JSON object of `sizeof` and `offsetof` values for the types in `REFERENCE_LAYOUTS.txt`. The program does not call `StartTrace`, `OpenTrace`, `ProcessTrace`, `StopTrace`, or `CloseTrace`. It does not load the Python ETW provider, create a logger, or change privileges. Product telemetry stays unavailable. The 66 product requirements are unchanged.

Five nested types have their own records as well as the original nine. `EVENT_HEADER_EXTENDED_DATA_ITEM` records `sizeof` and the addressable offsets `Reserved1`, `ExtType`, `DataSize`, and `DataPtr`. `Linkage` and `Reserved2` are a nameless `USHORT` bit-field, so there is no `offsetof` key for either name. One zeroed object is stored with an all-ones value in each bit-field. The changed byte span and the two masks are `Linkage_Reserved2_storage`, `Linkage_Reserved2_bytes`, `Linkage_mask`, and `Reserved2_mask`. Those four numbers are not `offsetof`. `GUID`, `SYSTEMTIME`, `TIME_ZONE_INFORMATION`, and `ETW_BUFFER_CONTEXT` record `sizeof` and `offsetof` for their SDK members. `SYSTEMTIME` uses the header's `w`-prefixed names. `ETW_BUFFER_CONTEXT` records both union arms, `ProcessorNumber` and `Alignment` beside `ProcessorIndex`, plus `LoggerId`. The existing primitive widths, including case-distinct `size_t` and `SIZE_T`, stay in `primitives`.

Supported targets are x64 (`arch` 1) and ARM64 (`arch` 2). x86, 32-bit ARM, ARM64EC, and any other architecture fail at compile time. The data model is LLP64.

The manual workflow `.github/workflows/windows-sdk-abi.yml` uses the free `windows-2022` runner as host x64 / target x64 and the free `windows-11-arm` runner as host ARM64 / target ARM64. It compiles with the MSVC and Windows SDK already on the runner, runs only this program, and uploads `abi.json` plus a separate short `metadata.json` (OS, host, target, PE machine, SDK version, compiler banner). It does not download a compiler.

Dispatch that workflow by hand after review. Do not treat the artifact as proof that tracing or telemetry is accepted.

The [31 October native SDK measurements](../../docs/validation/2026-10-31-windows-sdk-abi.md) passed on x64 and ARM64 with SDK 10.0.26100.0. The record retains all four original JSON artifacts and the earlier failed runs. FFI comparison, tracing and resource acceptance remain separate qualifications.
