# Windows SDK ABI oracle

This directory measures structure layout. It is not native tracing, and a run here is not resource acceptance.

`sdk_abi.c` includes the Windows SDK headers and prints one bounded JSON object of `sizeof` and `offsetof` values for the types in `REFERENCE_LAYOUTS.txt`. The program does not call `StartTrace`, `OpenTrace`, `ProcessTrace`, `StopTrace`, or `CloseTrace`. It does not load the Python ETW provider, create a logger, or change privileges. Product telemetry stays unavailable. The 66 product requirements are unchanged.

Supported targets are x64 (`arch` 1) and ARM64 (`arch` 2). x86, 32-bit ARM, ARM64EC, and any other architecture fail at compile time. The data model is LLP64.

The manual workflow `.github/workflows/windows-sdk-abi.yml` uses the free `windows-2022` runner as host x64 / target x64 and the free `windows-11-arm` runner as host ARM64 / target ARM64. It compiles with the MSVC and Windows SDK already on the runner, runs only this program, and uploads `abi.json` plus a separate short `metadata.json` (OS, host, target, PE machine, SDK version, compiler banner). It does not download a compiler.

Dispatch that workflow by hand after review. Do not treat the artifact as proof that tracing or telemetry is accepted.
