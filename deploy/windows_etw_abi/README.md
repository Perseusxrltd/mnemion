# Windows ETW declaration comparison

This directory checks the ctypes layouts declared in `deploy/owned_launch_windows_etw.py` against a frozen Windows SDK oracle. It does not start a session, load `advapi32` for the provider, or accept native resources. `declaration_match` is not production readiness and it is not CPU, RAM, or resource acceptance.

## Original SDK evidence

The expected numbers are the MSVC `sizeof` / `offsetof` oracle. They are not derived from the ctypes declarations.

- Source `781bef2e83532342a3bbcad99810e12875b2e046`
- GitHub Actions run `41237380248`
- Windows SDK `10.0.26100.0`, LLP64, native x64 and ARM64
- `oracle/manifest.json` is the provenance. It names the SHA-256 of `oracle/x64/abi.json`, `oracle/x64/metadata.json`, `oracle/arm64/abi.json`, and `oracle/arm64/metadata.json`
- `abi.json` holds the numeric layout. `metadata.json` holds host, compiler, and SDK identity. The checker does not read metadata fields as structure offsets
- The manifest records `trace_started: false`

`size_t` and `SIZE_T` stay separate keys. The provider file was not edited for this check.

The retained oracle has the nine structure records and the primitive widths. It does not have `GUID`, `SYSTEMTIME`, `TIME_ZONE_INFORMATION`, `ETW_BUFFER_CONTEXT`, or `EVENT_HEADER_EXTENDED_DATA_ITEM` field records. The checker recognizes those record names. It does not invent their offsets. Until a reviewed oracle supplies them and they match, complete coverage stays false.

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

The retained oracle has no `EVENT_HEADER_EXTENDED_DATA_ITEM` size or addressable offsets (`Reserved1`, `ExtType`, `DataSize`, `DataPtr`). `Linkage` and `Reserved2` are SDK bit-fields. The checker does not treat them as `offsetof` keys. A later oracle records that storage as `Linkage_Reserved2_storage`, `Linkage_Reserved2_bytes`, `Linkage_mask`, and `Reserved2_mask`. `SYSTEMTIME` fields use the SDK `w` prefix (`wYear`, `wMonth`, `wDayOfWeek`, `wDay`, `wHour`, `wMinute`, `wSecond`, `wMilliseconds`); the ctypes names do not. `ETW_BUFFER_CONTEXT` keeps both union arms (`ProcessorNumber`, `Alignment`, `ProcessorIndex`) and `LoggerId`. The ctypes declaration names `ProcessorIndex` and `LoggerId`. Primitive total widths are not those field layouts. SDK union aliases the provider does not declare are enumerated. The four retained JSON files and the manifest are unchanged, so this check still exits nonzero.
