# Windows ETW declaration comparison

This directory checks the ctypes layouts declared in `deploy/owned_launch_windows_etw.py` against a frozen Windows SDK oracle. It does not start a session, load `advapi32` for the provider, or accept native resources. `declaration_match` is not production readiness and it is not CPU, RAM, or resource acceptance.

## SDK evidence

The expected numbers are the MSVC `sizeof` / `offsetof` oracle. They are not derived from the ctypes declarations.

- Source `f49ab34923d018efb3d2d30beb3a954aa6b73a48`
- GitHub Actions run `41244785682`
- Windows SDK `10.0.26100.0`, LLP64, native x64 and ARM64
- `oracle/manifest.json` is the provenance. It names the SHA-256 of `oracle/x64/abi.json`, `oracle/x64/metadata.json`, `oracle/arm64/abi.json`, and `oracle/arm64/metadata.json`
- `abi.json` holds the numeric layout. `metadata.json` holds host, compiler, and SDK identity. The checker does not read metadata fields as structure offsets
- The manifest records `trace_started: false`

`size_t` and `SIZE_T` stay separate keys. The provider file was not edited for this check.

The retained oracle measures fourteen structure records: the original nine, plus `GUID`, `SYSTEMTIME`, `TIME_ZONE_INFORMATION`, `ETW_BUFFER_CONTEXT`, and `EVENT_HEADER_EXTENDED_DATA_ITEM`, and the primitive widths. Those sizes and addressable offsets are the MSVC measurements from run `41244785682`. They are not derived from the ctypes declarations.

## Command

The workflow `.github/workflows/windows-etw-abi.yml` is manual (`workflow_dispatch` only). It checks out read-only (`contents: read`), uses the repository's pinned setup-python action, and selects `architecture: x64` on `windows-2022` or `architecture: arm64` on `windows-11-arm`. The helper reads the Python executable's PE machine before comparing. An x64 interpreter running under emulation is not ARM64 evidence.

```text
python deploy/windows_etw_abi/compare_declarations.py --arch x64 --receipt output/windows-etw-abi/declaration-receipt.json
```

Use `--arch arm64` only with native ARM64 Python. Exit 0 requires both `covered_field_match` and `complete_coverage`. Covered field match means the fields that were compared agree with the oracle. Complete coverage means every required SDK measurement is present and matched, including the extended item's size and addressable offsets. A covered-field match with missing required layouts is not a complete declaration match and exits nonzero. The receipt still lists the fields that matched. The workflow uploads only `declaration-receipt.json`.

The helper resolves `deploy/owned_launch_windows_etw.py` first, reads that file once under a size bound, and hashes that buffer. It compiles and executes those exact bytes as the module `deploy.owned_launch_windows_etw`. It does not import the provider through `importlib`, and it does not load a cached `.pyc`. The receipt's provider SHA-256 is the hash of the executed buffer.

CPython's ctypes import binds `kernel32.GetLastError`. The helper then refuses any further `CDLL` / `WinDLL` / `OleDLL` / `PyDLL` construction and requires `native_api_loaded` to stay false. It does not construct `WinEtwApi`, `AdapterOwnership`, an observer, a callback, or a job.

The receipt keeps numeric layout results apart from metadata. It records covered field match, complete coverage, required missing layouts, and the executed source hash, plus the hashes of both frozen oracle architectures. `native_tracing`, emission, and CPU, RAM, and resource acceptance stay false.

## Still open

A declaration comparison does not open these gates:

- actual ETW
- session owner
- deadline
- cleanup
- clock
- counter
- loss
- census
- observer cost

`EVENT_HEADER_EXTENDED_DATA_ITEM` is measured, including `Reserved1`, `ExtType`, `DataSize`, and `DataPtr`. `Linkage` and `Reserved2` remain SDK bit-fields. The checker does not treat them as `offsetof` keys and does not claim the provider declares those two bit-fields. The provider's opaque `Linkage` USHORT is the container compared with `Linkage_Reserved2_storage` and `Linkage_Reserved2_bytes`. `Linkage_mask` and `Reserved2_mask` stay SDK-only experiment values. `SYSTEMTIME` fields use the SDK `w` prefix (`wYear`, `wMonth`, `wDayOfWeek`, `wDay`, `wHour`, `wMinute`, `wSecond`, `wMilliseconds`); the ctypes names do not. `ETW_BUFFER_CONTEXT` compares `ProcessorIndex` and `LoggerId`. `ProcessorNumber` and `Alignment` stay SDK-only union arms. This note does not claim an executed declaration comparison, a trace, or CPU, RAM, or resource acceptance.
