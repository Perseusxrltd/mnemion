"""Compare provider ctypes layouts with the frozen Windows SDK oracle.

The expected numbers come only from deploy/windows_etw_abi/oracle/.
This process does not start ETW, load advapi32 for the provider, or compile
a C oracle. It does not accept native resources, CPU, or RAM.

Exit 0 requires covered_field_match and complete_coverage. Fields that were
compared can match while required SDK layouts are still absent. That receipt
is not a complete declaration match. Missing required extended size or
addressable offsets exits nonzero. This file does not invent those numbers.

The intended provider path is resolved first. Its source is read once, at
most PROVIDER_SOURCE_LIMIT + 1 bytes. Oversize input is rejected. The
retained buffer is hashed, then compiled and executed as
deploy.owned_launch_windows_etw. importlib and a cached .pyc are not the
provider.

CPython's ctypes import binds kernel32.GetLastError. Further
CDLL/WinDLL/OleDLL/PyDLL construction is refused before those bytes execute.
That refusal does not make the rest of CPython API-free.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
import types
from pathlib import Path


CHECK = "windows_etw_declaration_comparison"
ORACLE_SOURCE = "f49ab34923d018efb3d2d30beb3a954aa6b73a48"
ORACLE_RUN = 41244785682
SDK_VERSION = "10.0.26100.0"
ARCHES = ("x64", "arm64")
PE_MACHINE = {"x64": 0x8664, "arm64": 0xAA64}
PLATFORM_MACHINE = {"x64": "AMD64", "arm64": "ARM64"}
ORACLE_ARCH = {"x64": 1, "arm64": 2}
RUNNER_ARCH = {"x64": "X64", "arm64": "ARM64"}
NINE = (
    "WNODE_HEADER",
    "EVENT_TRACE_PROPERTIES",
    "EVENT_DESCRIPTOR",
    "EVENT_HEADER",
    "EVENT_RECORD",
    "EVENT_TRACE_HEADER",
    "EVENT_TRACE",
    "TRACE_LOGFILE_HEADER",
    "EVENT_TRACE_LOGFILEW",
)
DIRECT_PRIMITIVES = {
    "int": "c_int",
    "long": "c_long",
    "long_long": "c_longlong",
    "pointer": "c_void_p",
    "wchar_t": "c_wchar",
    "size_t": "c_size_t",
    "SIZE_T": "c_size_t",
    "UCHAR": "c_ubyte",
    "USHORT": "c_ushort",
    "ULONG": "c_ulong",
    "WCHAR": "c_wchar",
    "HANDLE": "c_void_p",
    "LONGLONG": "c_longlong",
    "ULONGLONG": "c_ulonglong",
    "LARGE_INTEGER": "c_longlong",
}
PROVIDER_PRIMITIVES = {
    "GUID": "_GUID",
    "TIME_ZONE_INFORMATION": "_TIME_ZONE_INFORMATION",
    "ETW_BUFFER_CONTEXT": "_ETW_BUFFER_CONTEXT",
}
RECORDED_PRIMITIVES = (
    "char",
    "short",
    "ptrdiff_t",
    "uintptr_t",
    "int32_t",
    "int64_t",
    "BOOL",
    "BOOLEAN",
    "ULONG_PTR",
)
ALIASES = {
    "EVENT_TRACE_PROPERTIES": ("FlushThreshold",),
    "EVENT_HEADER": ("KernelTime", "UserTime"),
    "EVENT_TRACE": ("ClientContext",),
    "TRACE_LOGFILE_HEADER": (
        "VersionDetail",
        "VersionDetail_MajorVersion",
        "VersionDetail_MinorVersion",
        "VersionDetail_SubVersion",
        "VersionDetail_SubMinorVersion",
        "StartBuffers",
        "PointerSize",
        "EventsLost",
        "CpuSpeedInMHz",
    ),
    "EVENT_TRACE_LOGFILEW": ("LogFileMode", "EventCallback"),
}
MAX_ITEMS = 32
LAYOUT_LIMIT = 1024
PROVIDER_SOURCE_LIMIT = 2_000_000
PROVIDER_MODULE = "deploy.owned_launch_windows_etw"
EXTENDED_PROVIDER_USE = {
    "Reserved1": "declared_not_read",
    "ExtType": "read",
    "Linkage": "declared_not_read",
    "DataSize": "declared_not_read",
    "DataPtr": "declared_not_read",
}

GUID_FIELDS = (
    ("Data1", None, ("primitive", "ULONG"), "scalar", None),
    ("Data2", None, ("primitive", "USHORT"), "scalar", None),
    ("Data3", None, ("primitive", "USHORT"), "scalar", None),
    ("Data4", None, ("array", "UCHAR", 8), "scalar", None),
)
SYSTEMTIME_FIELDS = tuple(
    (name, None, ("primitive", "USHORT"), "scalar", None)
    for name in (
        "Year",
        "Month",
        "DayOfWeek",
        "Day",
        "Hour",
        "Minute",
        "Second",
        "Milliseconds",
    )
)
BUFFER_FIELDS = (
    ("ProcessorIndex", None, ("primitive", "USHORT"), "scalar", None),
    ("LoggerId", None, ("primitive", "USHORT"), "scalar", None),
)
TIME_ZONE_FIELDS = (
    ("Bias", None, ("primitive", "long"), "scalar", None),
    ("StandardName", None, ("array", "WCHAR", 32), "scalar", None),
    ("StandardDate", None, None, "aggregate", SYSTEMTIME_FIELDS),
    ("StandardBias", None, ("primitive", "long"), "scalar", None),
    ("DaylightName", None, ("array", "WCHAR", 32), "scalar", None),
    ("DaylightDate", None, None, "aggregate", SYSTEMTIME_FIELDS),
    ("DaylightBias", None, ("primitive", "long"), "scalar", None),
)

STRUCTURES = (
    (
        "WNODE_HEADER",
        "_WNODE_HEADER",
        (
            ("BufferSize", "BufferSize", ("primitive", "ULONG"), "scalar", None),
            ("ProviderId", "ProviderId", ("primitive", "ULONG"), "scalar", None),
            (
                "Historical",
                None,
                None,
                "union",
                (
                    ("HistoricalContext", "HistoricalContext", ("primitive", "ULONGLONG"), "scalar", None),
                    (
                        "VersionLinkage",
                        None,
                        None,
                        "struct",
                        (
                            ("Version", "Version", ("primitive", "ULONG"), "scalar", None),
                            ("Linkage", "Linkage", ("primitive", "ULONG"), "scalar", None),
                        ),
                    ),
                ),
            ),
            (
                "Timestamp",
                None,
                None,
                "union",
                (
                    (
                        "CountLost",
                        None,
                        None,
                        "struct",
                        (("CountLost", "CountLost", ("primitive", "ULONG"), "scalar", None),),
                    ),
                    ("KernelHandle", "KernelHandle", ("primitive", "HANDLE"), "scalar", None),
                    ("TimeStamp", "TimeStamp", ("primitive", "LARGE_INTEGER"), "scalar", None),
                ),
            ),
            ("Guid", "Guid", ("primitive", "GUID"), "aggregate", GUID_FIELDS),
            ("ClientContext", "ClientContext", ("primitive", "ULONG"), "scalar", None),
            ("Flags", "Flags", ("primitive", "ULONG"), "scalar", None),
        ),
    ),
    (
        "EVENT_TRACE_PROPERTIES",
        "_EVENT_TRACE_PROPERTIES",
        (
            ("Wnode", "Wnode", ("structure", "WNODE_HEADER"), "struct", None),
            ("BufferSize", "BufferSize", ("primitive", "ULONG"), "scalar", None),
            ("MinimumBuffers", "MinimumBuffers", ("primitive", "ULONG"), "scalar", None),
            ("MaximumBuffers", "MaximumBuffers", ("primitive", "ULONG"), "scalar", None),
            ("MaximumFileSize", "MaximumFileSize", ("primitive", "ULONG"), "scalar", None),
            ("LogFileMode", "LogFileMode", ("primitive", "ULONG"), "scalar", None),
            ("FlushTimer", "FlushTimer", ("primitive", "ULONG"), "scalar", None),
            ("EnableFlags", "EnableFlags", ("primitive", "ULONG"), "scalar", None),
            ("AgeLimit", "AgeLimit", ("primitive", "long"), "scalar", None),
            ("NumberOfBuffers", "NumberOfBuffers", ("primitive", "ULONG"), "scalar", None),
            ("FreeBuffers", "FreeBuffers", ("primitive", "ULONG"), "scalar", None),
            ("EventsLost", "EventsLost", ("primitive", "ULONG"), "scalar", None),
            ("BuffersWritten", "BuffersWritten", ("primitive", "ULONG"), "scalar", None),
            ("LogBuffersLost", "LogBuffersLost", ("primitive", "ULONG"), "scalar", None),
            ("RealTimeBuffersLost", "RealTimeBuffersLost", ("primitive", "ULONG"), "scalar", None),
            ("LoggerThreadId", "LoggerThreadId", ("primitive", "HANDLE"), "scalar", None),
            ("LogFileNameOffset", "LogFileNameOffset", ("primitive", "ULONG"), "scalar", None),
            ("LoggerNameOffset", "LoggerNameOffset", ("primitive", "ULONG"), "scalar", None),
        ),
    ),
    (
        "EVENT_DESCRIPTOR",
        "_EVENT_DESCRIPTOR",
        (
            ("Id", "Id", ("primitive", "USHORT"), "scalar", None),
            ("Version", "Version", ("primitive", "UCHAR"), "scalar", None),
            ("Channel", "Channel", ("primitive", "UCHAR"), "scalar", None),
            ("Level", "Level", ("primitive", "UCHAR"), "scalar", None),
            ("Opcode", "Opcode", ("primitive", "UCHAR"), "scalar", None),
            ("Task", "Task", ("primitive", "USHORT"), "scalar", None),
            ("Keyword", "Keyword", ("primitive", "ULONGLONG"), "scalar", None),
        ),
    ),
    (
        "EVENT_HEADER",
        "_EVENT_HEADER",
        (
            ("Size", "Size", ("primitive", "USHORT"), "scalar", None),
            ("HeaderType", "HeaderType", ("primitive", "USHORT"), "scalar", None),
            ("Flags", "Flags", ("primitive", "USHORT"), "scalar", None),
            ("EventProperty", "EventProperty", ("primitive", "USHORT"), "scalar", None),
            ("ThreadId", "ThreadId", ("primitive", "ULONG"), "scalar", None),
            ("ProcessId", "ProcessId", ("primitive", "ULONG"), "scalar", None),
            ("TimeStamp", "TimeStamp", ("primitive", "LARGE_INTEGER"), "scalar", None),
            ("ProviderId", "ProviderId", ("primitive", "GUID"), "aggregate", GUID_FIELDS),
            ("EventDescriptor", "EventDescriptor", ("structure", "EVENT_DESCRIPTOR"), "struct", None),
            ("ProcessorTime", "ProcessorTime", ("primitive", "ULONGLONG"), "scalar", None),
            ("ActivityId", "ActivityId", ("primitive", "GUID"), "aggregate", GUID_FIELDS),
        ),
    ),
    (
        "EVENT_RECORD",
        "_EVENT_RECORD",
        (
            ("EventHeader", "EventHeader", ("structure", "EVENT_HEADER"), "struct", None),
            ("BufferContext", "BufferContext", ("primitive", "ETW_BUFFER_CONTEXT"), "aggregate", BUFFER_FIELDS),
            ("ExtendedDataCount", "ExtendedDataCount", ("primitive", "USHORT"), "scalar", None),
            ("UserDataLength", "UserDataLength", ("primitive", "USHORT"), "scalar", None),
            ("ExtendedData", "ExtendedData", ("primitive", "pointer"), "scalar", None),
            ("UserData", "UserData", ("primitive", "pointer"), "scalar", None),
            ("UserContext", "UserContext", ("primitive", "pointer"), "scalar", None),
        ),
    ),
    (
        "EVENT_TRACE_HEADER",
        "_EVENT_TRACE_HEADER",
        (
            ("Size", "Size", ("primitive", "USHORT"), "scalar", None),
            (
                "FieldType",
                None,
                None,
                "union",
                (
                    ("FieldTypeFlags", "FieldTypeFlags", ("primitive", "USHORT"), "scalar", None),
                    (
                        "HeaderBytes",
                        None,
                        None,
                        "struct",
                        (
                            ("HeaderType", "HeaderType", ("primitive", "UCHAR"), "scalar", None),
                            ("MarkerFlags", "MarkerFlags", ("primitive", "UCHAR"), "scalar", None),
                        ),
                    ),
                ),
            ),
            (
                "Version",
                None,
                None,
                "union",
                (
                    ("Version", "Version", ("primitive", "ULONG"), "scalar", None),
                    (
                        "Class",
                        "Class",
                        ("primitive", "ULONG"),
                        "aggregate",
                        (
                            ("Type", "Class_Type", ("primitive", "UCHAR"), "scalar", None),
                            ("Level", "Class_Level", ("primitive", "UCHAR"), "scalar", None),
                            ("Version", "Class_Version", ("primitive", "USHORT"), "scalar", None),
                        ),
                    ),
                ),
            ),
            ("ThreadId", "ThreadId", ("primitive", "ULONG"), "scalar", None),
            ("ProcessId", "ProcessId", ("primitive", "ULONG"), "scalar", None),
            ("TimeStamp", "TimeStamp", ("primitive", "LARGE_INTEGER"), "scalar", None),
            (
                "Guid",
                None,
                None,
                "union",
                (
                    ("Guid", "Guid", ("primitive", "GUID"), "aggregate", GUID_FIELDS),
                    ("GuidPtr", "GuidPtr", ("primitive", "ULONGLONG"), "scalar", None),
                ),
            ),
            (
                "Times",
                None,
                None,
                "union",
                (
                    (
                        "KernelUser",
                        None,
                        None,
                        "struct",
                        (
                            ("KernelTime", "KernelTime", ("primitive", "ULONG"), "scalar", None),
                            ("UserTime", "UserTime", ("primitive", "ULONG"), "scalar", None),
                        ),
                    ),
                    ("ProcessorTime", "ProcessorTime", ("primitive", "ULONGLONG"), "scalar", None),
                    (
                        "ClientFlags",
                        None,
                        None,
                        "struct",
                        (
                            ("ClientContext", "ClientContext", ("primitive", "ULONG"), "scalar", None),
                            ("Flags", "Flags", ("primitive", "ULONG"), "scalar", None),
                        ),
                    ),
                ),
            ),
        ),
    ),
    (
        "EVENT_TRACE",
        "_EVENT_TRACE",
        (
            ("Header", "Header", ("structure", "EVENT_TRACE_HEADER"), "struct", None),
            ("InstanceId", "InstanceId", ("primitive", "ULONG"), "scalar", None),
            ("ParentInstanceId", "ParentInstanceId", ("primitive", "ULONG"), "scalar", None),
            ("ParentGuid", "ParentGuid", ("primitive", "GUID"), "aggregate", GUID_FIELDS),
            ("MofData", "MofData", ("primitive", "pointer"), "scalar", None),
            ("MofLength", "MofLength", ("primitive", "ULONG"), "scalar", None),
            ("BufferContext", "BufferContext", ("primitive", "ETW_BUFFER_CONTEXT"), "aggregate", BUFFER_FIELDS),
        ),
    ),
    (
        "TRACE_LOGFILE_HEADER",
        "_TRACE_LOGFILE_HEADER",
        (
            ("BufferSize", "BufferSize", ("primitive", "ULONG"), "scalar", None),
            ("Version", "Version", ("primitive", "ULONG"), "scalar", None),
            ("ProviderVersion", "ProviderVersion", ("primitive", "ULONG"), "scalar", None),
            ("NumberOfProcessors", "NumberOfProcessors", ("primitive", "ULONG"), "scalar", None),
            ("EndTime", "EndTime", ("primitive", "LARGE_INTEGER"), "scalar", None),
            ("TimerResolution", "TimerResolution", ("primitive", "ULONG"), "scalar", None),
            ("MaximumFileSize", "MaximumFileSize", ("primitive", "ULONG"), "scalar", None),
            ("LogFileMode", "LogFileMode", ("primitive", "ULONG"), "scalar", None),
            ("BuffersWritten", "BuffersWritten", ("primitive", "ULONG"), "scalar", None),
            ("LogInstanceGuid", "LogInstanceGuid", ("primitive", "GUID"), "aggregate", GUID_FIELDS),
            ("LoggerName", "LoggerName", ("primitive", "pointer"), "scalar", None),
            ("LogFileName", "LogFileName", ("primitive", "pointer"), "scalar", None),
            ("TimeZone", "TimeZone", ("primitive", "TIME_ZONE_INFORMATION"), "aggregate", TIME_ZONE_FIELDS),
            ("BootTime", "BootTime", ("primitive", "LARGE_INTEGER"), "scalar", None),
            ("PerfFreq", "PerfFreq", ("primitive", "LARGE_INTEGER"), "scalar", None),
            ("StartTime", "StartTime", ("primitive", "LARGE_INTEGER"), "scalar", None),
            ("ReservedFlags", "ReservedFlags", ("primitive", "ULONG"), "scalar", None),
            ("BuffersLost", "BuffersLost", ("primitive", "ULONG"), "scalar", None),
        ),
    ),
    (
        "EVENT_TRACE_LOGFILEW",
        "_EVENT_TRACE_LOGFILEW",
        (
            ("LogFileName", "LogFileName", ("primitive", "pointer"), "scalar", None),
            ("LoggerName", "LoggerName", ("primitive", "pointer"), "scalar", None),
            ("CurrentTime", "CurrentTime", ("primitive", "LARGE_INTEGER"), "scalar", None),
            ("BuffersRead", "BuffersRead", ("primitive", "ULONG"), "scalar", None),
            ("ProcessTraceMode", "ProcessTraceMode", ("primitive", "ULONG"), "scalar", None),
            ("CurrentEvent", "CurrentEvent", ("structure", "EVENT_TRACE"), "struct", None),
            ("LogfileHeader", "LogfileHeader", ("structure", "TRACE_LOGFILE_HEADER"), "struct", None),
            ("BufferCallback", "BufferCallback", ("primitive", "pointer"), "scalar", None),
            ("BufferSize", "BufferSize", ("primitive", "ULONG"), "scalar", None),
            ("Filled", "Filled", ("primitive", "ULONG"), "scalar", None),
            ("EventsLost", "EventsLost", ("primitive", "ULONG"), "scalar", None),
            ("EventRecordCallback", "EventRecordCallback", ("primitive", "pointer"), "scalar", None),
            ("IsKernelTrace", "IsKernelTrace", ("primitive", "ULONG"), "scalar", None),
            ("Context", "Context", ("primitive", "pointer"), "scalar", None),
        ),
    ),
)
EXTENDED_FIELDS = (
    ("Reserved1", None, ("primitive", "USHORT"), "scalar", None),
    ("ExtType", None, ("primitive", "USHORT"), "scalar", None),
    ("Linkage", None, ("primitive", "USHORT"), "scalar", None),
    ("DataSize", None, ("primitive", "USHORT"), "scalar", None),
    ("DataPtr", None, ("primitive", "ULONGLONG"), "scalar", None),
)
# Nested walks keep provider names unbound so they are not looked up on the parent.
# Linkage and Reserved2 have no offsetof key. The four experiment keys are not offsets.
# Linkage_Reserved2_storage/bytes is the measured container span. It is compared
# with the provider's one opaque Linkage USHORT. The masks stay SDK-only.
# The provider does not declare or read those two bit-fields.
EXPANDED_RECORDS = (
    (
        "GUID",
        "_GUID",
        ("Data1", "Data2", "Data3", "Data4"),
        (
            ("Data1", "Data1", ("primitive", "ULONG")),
            ("Data2", "Data2", ("primitive", "USHORT")),
            ("Data3", "Data3", ("primitive", "USHORT")),
            ("Data4", "Data4", ("array", "UCHAR", 8)),
        ),
        (),
        None,
        (),
        True,
    ),
    (
        "SYSTEMTIME",
        "_SYSTEMTIME",
        ("Year", "Month", "DayOfWeek", "Day", "Hour", "Minute", "Second", "Milliseconds"),
        (
            ("Year", "wYear", ("primitive", "USHORT")),
            ("Month", "wMonth", ("primitive", "USHORT")),
            ("DayOfWeek", "wDayOfWeek", ("primitive", "USHORT")),
            ("Day", "wDay", ("primitive", "USHORT")),
            ("Hour", "wHour", ("primitive", "USHORT")),
            ("Minute", "wMinute", ("primitive", "USHORT")),
            ("Second", "wSecond", ("primitive", "USHORT")),
            ("Milliseconds", "wMilliseconds", ("primitive", "USHORT")),
        ),
        (),
        None,
        (),
        False,
    ),
    (
        "TIME_ZONE_INFORMATION",
        "_TIME_ZONE_INFORMATION",
        (
            "Bias",
            "StandardName",
            "StandardDate",
            "StandardBias",
            "DaylightName",
            "DaylightDate",
            "DaylightBias",
        ),
        (
            ("Bias", "Bias", ("primitive", "long")),
            ("StandardName", "StandardName", ("array", "WCHAR", 32)),
            ("StandardDate", "StandardDate", ("structure", "SYSTEMTIME")),
            ("StandardBias", "StandardBias", ("primitive", "long")),
            ("DaylightName", "DaylightName", ("array", "WCHAR", 32)),
            ("DaylightDate", "DaylightDate", ("structure", "SYSTEMTIME")),
            ("DaylightBias", "DaylightBias", ("primitive", "long")),
        ),
        (),
        None,
        (),
        True,
    ),
    (
        "ETW_BUFFER_CONTEXT",
        "_ETW_BUFFER_CONTEXT",
        ("ProcessorIndex", "LoggerId"),
        (
            ("ProcessorIndex", "ProcessorIndex", ("primitive", "USHORT")),
            ("LoggerId", "LoggerId", ("primitive", "USHORT")),
        ),
        ("ProcessorNumber", "Alignment"),
        "ProcessorIndex",
        (),
        True,
    ),
    (
        "EVENT_HEADER_EXTENDED_DATA_ITEM",
        "_EVENT_HEADER_EXTENDED_DATA_ITEM",
        ("Reserved1", "ExtType", "Linkage", "DataSize", "DataPtr"),
        (
            ("Reserved1", "Reserved1", ("primitive", "USHORT")),
            ("ExtType", "ExtType", ("primitive", "USHORT")),
            ("DataSize", "DataSize", ("primitive", "USHORT")),
            ("DataPtr", "DataPtr", ("primitive", "ULONGLONG")),
        ),
        (),
        None,
        (
            "Linkage_Reserved2_storage",
            "Linkage_Reserved2_bytes",
            "Linkage_mask",
            "Reserved2_mask",
        ),
        False,
    ),
)
EXPANDED_RECORD_NAMES = frozenset(item[0] for item in EXPANDED_RECORDS)
EXPANDED_PROVIDER_TYPES = frozenset(item[1] for item in EXPANDED_RECORDS)
MEASUREMENT_UINT64 = (1 << 64) - 1


class LayoutMiss(Exception):
    def __init__(self, kind, **detail):
        self.kind = kind
        self.detail = detail
        super().__init__(kind)


def _sha256(path: Path, limit: int) -> str:
    data = path.read_bytes()
    if len(data) > limit:
        raise LayoutMiss("file_too_large", name=path.name, bytes=len(data))
    return hashlib.sha256(data).hexdigest()


def _load_json(path: Path, limit: int) -> dict:
    raw = path.read_bytes()
    if len(raw) > limit:
        raise LayoutMiss("file_too_large", name=path.name, bytes=len(raw))
    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        raise LayoutMiss("json_encoding", name=path.name) from exc

    def pairs(items):
        obj = {}
        for key, value in items:
            if type(key) is not str or key in obj:
                raise LayoutMiss("duplicate_or_non_string_key", name=path.name)
            obj[key] = value
        return obj

    try:
        def reject_constant(_name):
            raise LayoutMiss("json_constant", name=path.name)

        value = json.loads(text, object_pairs_hook=pairs, parse_constant=reject_constant)
    except LayoutMiss:
        raise
    except (json.JSONDecodeError, ValueError) as exc:
        raise LayoutMiss("json_parse", name=path.name) from exc
    if type(value) is not dict:
        raise LayoutMiss("json_object", name=path.name)
    return value


def _layout_int(value):
    if type(value) is not int or value < 0 or value > LAYOUT_LIMIT:
        return None
    return value


def _field_offset(descriptor):
    if hasattr(descriptor, "offset"):
        return descriptor.offset
    if hasattr(descriptor, "byte_offset"):
        return descriptor.byte_offset
    return None


def _declared_fields(cls):
    fields = getattr(cls, "_fields_", None)
    if type(fields) not in (list, tuple) or not fields:
        raise LayoutMiss("missing_fields", type=getattr(cls, "__name__", ""))
    declared = []
    seen = set()
    for item in fields:
        if type(item) is not tuple or len(item) < 2 or len(item) > 3:
            raise LayoutMiss("bad_field_declaration", type=cls.__name__)
        if len(item) == 3:
            raise LayoutMiss("bitfield_not_compared", type=cls.__name__, field=str(item[0])[:80])
        name, declared_type = item[0], item[1]
        if type(name) is not str or name in seen:
            raise LayoutMiss("bad_field_name", type=cls.__name__)
        seen.add(name)
        declared.append((name, declared_type))
    return declared


def _resolve_width(abi, width):
    if width is None:
        return None
    kind = width[0]
    if kind == "primitive":
        table = abi.get("primitives")
        if type(table) is not dict or width[1] not in table:
            raise LayoutMiss("missing_primitive", key=width[1])
        value = _layout_int(table[width[1]])
        if value is None or value == 0:
            raise LayoutMiss("bad_primitive_width", key=width[1])
        return value
    if kind == "structure":
        block = abi.get(width[1])
        if type(block) is not dict or "sizeof" not in block:
            raise LayoutMiss("missing_structure", name=width[1])
        value = _layout_int(block["sizeof"])
        if value is None or value == 0:
            raise LayoutMiss("bad_structure_width", name=width[1])
        return value
    if kind == "array":
        one = _resolve_width(abi, ("primitive", width[1]))
        count = width[2]
        if type(count) is not int or count < 1 or count > 64:
            raise LayoutMiss("bad_array", key=width[1])
        return one * count
    raise LayoutMiss("bad_width_spec")


def _bindings(fields, prefix=""):
    found = []
    for name, sdk, width, _kind, children in fields:
        path = name if not prefix else prefix + "." + name
        if sdk is not None:
            found.append((path, sdk, width))
        if children:
            found.extend(_bindings(children, path))
    return found


def _expected_map(abi):
    expected = {}
    ranges = {name: [] for name in NINE}
    for struct_name, _class_name, fields in STRUCTURES:
        block = abi.get(struct_name)
        if type(block) is not dict:
            raise LayoutMiss("missing_required_data", key=struct_name)
        for path, sdk, width in _bindings(fields):
            if sdk in expected.get(struct_name, {}):
                raise LayoutMiss("duplicate_binding", structure=struct_name, field=sdk)
            if sdk not in block:
                raise LayoutMiss("missing_sdk_field", structure=struct_name, field=sdk, path=path)
            offset = _layout_int(block[sdk])
            field_width = _resolve_width(abi, width)
            if offset is None or field_width is None:
                raise LayoutMiss("bad_sdk_number", structure=struct_name, field=sdk)
            expected.setdefault(struct_name, {})[sdk] = (offset, field_width, path)
            ranges[struct_name].append((offset, offset + field_width, sdk))
    return expected, ranges


def _classify_sdk_fields(abi, expected, ranges, mismatches):
    aliases = []
    for struct_name in NINE:
        block = abi[struct_name]
        keys = {key for key in block if key != "sizeof"}
        bound = set(expected[struct_name])
        named = set(ALIASES.get(struct_name, ()))
        unknown = sorted(keys - bound - named)
        unused_alias = sorted(named - keys)
        for field in unknown:
            _add(mismatches, "unclassified_sdk_field", structure=struct_name, field=field)
        for field in unused_alias:
            _add(mismatches, "alias_not_in_sdk", structure=struct_name, field=field)
        for field in sorted(named & keys):
            offset = _layout_int(block[field])
            if offset is None:
                _add(mismatches, "bad_sdk_number", structure=struct_name, field=field)
                continue
            covered = any(start <= offset < end for start, end, _sdk in ranges[struct_name])
            if not covered:
                _add(mismatches, "alias_not_overlay", structure=struct_name, field=field, offset=offset)
            aliases.append({"structure": struct_name, "field": field, "offset": offset, "represented": False})
    return aliases


def _add(mismatches, kind, **detail):
    real = [item for item in mismatches if item.get("kind") != "omitted"]
    if len(real) < MAX_ITEMS:
        item = {"kind": kind}
        item.update(detail)
        mismatches.append(item)
        return
    for item in mismatches:
        if item.get("kind") == "omitted":
            item["count"] = int(item.get("count", 0)) + 1
            return
    mismatches.append({"kind": "omitted", "count": 1})


def _check_type_shape(cls):
    pack = getattr(cls, "_pack_", None)
    if pack not in (None, 0):
        raise LayoutMiss("pack_set", type=cls.__name__)
    if getattr(cls, "_anonymous_", None):
        raise LayoutMiss("anonymous_fields", type=cls.__name__)


CLASS_FOR_STRUCTURE = {name: class_name for name, class_name, _fields in STRUCTURES}
AGGREGATE_TYPE = {
    "GUID": "_GUID",
    "ETW_BUFFER_CONTEXT": "_ETW_BUFFER_CONTEXT",
    "TIME_ZONE_INFORMATION": "_TIME_ZONE_INFORMATION",
}
UNSIZED_AGGREGATE = {"StandardDate": "_SYSTEMTIME", "DaylightDate": "_SYSTEMTIME"}
# Nested walk leaves whose offsets are measured on an expanded record, not on the parent.
_NESTED_EXPANDED_FIELD = {
    "Data1": ("GUID", "Data1"),
    "Data2": ("GUID", "Data2"),
    "Data3": ("GUID", "Data3"),
    "Data4": ("GUID", "Data4"),
    "Year": ("SYSTEMTIME", "wYear"),
    "Month": ("SYSTEMTIME", "wMonth"),
    "DayOfWeek": ("SYSTEMTIME", "wDayOfWeek"),
    "Day": ("SYSTEMTIME", "wDay"),
    "Hour": ("SYSTEMTIME", "wHour"),
    "Minute": ("SYSTEMTIME", "wMinute"),
    "Second": ("SYSTEMTIME", "wSecond"),
    "Milliseconds": ("SYSTEMTIME", "wMilliseconds"),
    "Bias": ("TIME_ZONE_INFORMATION", "Bias"),
    "StandardName": ("TIME_ZONE_INFORMATION", "StandardName"),
    "StandardDate": ("TIME_ZONE_INFORMATION", "StandardDate"),
    "StandardBias": ("TIME_ZONE_INFORMATION", "StandardBias"),
    "DaylightName": ("TIME_ZONE_INFORMATION", "DaylightName"),
    "DaylightDate": ("TIME_ZONE_INFORMATION", "DaylightDate"),
    "DaylightBias": ("TIME_ZONE_INFORMATION", "DaylightBias"),
    "ProcessorIndex": ("ETW_BUFFER_CONTEXT", "ProcessorIndex"),
    "LoggerId": ("ETW_BUFFER_CONTEXT", "LoggerId"),
}


def _walk(cls, fields, base, struct_name, abi, expected, module, mismatches, visited, width_only, without_oracle, unmeasured, matched, compare_offsets, prefix):
    import ctypes

    visited.add(cls.__name__)
    _check_type_shape(cls)
    if issubclass(cls, ctypes.Union) and issubclass(cls, ctypes.Structure):
        raise LayoutMiss("ambiguous_type", type=cls.__name__)
    declared = _declared_fields(cls)
    spec_names = [item[0] for item in fields]
    actual_names = [name for name, _declared in declared]
    if actual_names != spec_names:
        _add(
            mismatches,
            "field_set",
            structure=struct_name,
            type=cls.__name__,
            provider=actual_names,
            represented=spec_names,
        )
    actual = {name: declared_type for name, declared_type in declared}
    is_union = issubclass(cls, ctypes.Union)
    for name, sdk, width, kind, children in fields:
        path = name if not prefix else prefix + "." + name
        if name not in actual:
            _add(mismatches, "missing_provider_field", structure=struct_name, field=sdk or name, path=path)
            continue
        declared_type = actual[name]
        descriptor = getattr(cls, name, None)
        rel = None if descriptor is None else _layout_int(_field_offset(descriptor))
        if rel is None:
            _add(mismatches, "missing_offset", structure=struct_name, field=sdk or name, path=path, type=cls.__name__)
            continue
        if is_union and rel != 0:
            _add(mismatches, "union_member_offset", structure=struct_name, field=name, path=path, offset=rel)
        absolute = base + rel
        try:
            actual_width = ctypes.sizeof(declared_type)
        except (TypeError, ValueError):
            _add(mismatches, "width_unavailable", structure=struct_name, field=sdk or name, path=path)
            continue
        if type(actual_width) is not int:
            _add(mismatches, "width_unavailable", structure=struct_name, field=sdk or name, path=path)
            continue
        reported = getattr(descriptor, "size", None)
        if reported is not None and _layout_int(reported) != actual_width:
            _add(mismatches, "descriptor_width", structure=struct_name, field=name, path=path)
        if kind == "union":
            if not (isinstance(declared_type, type) and issubclass(declared_type, ctypes.Union)):
                _add(mismatches, "not_union", structure=struct_name, field=name, path=path)
        elif kind in ("struct", "aggregate"):
            if not (isinstance(declared_type, type) and issubclass(declared_type, ctypes.Structure)):
                _add(mismatches, "not_structure", structure=struct_name, field=name, path=path)
        if width is not None and width[0] == "structure":
            wanted = getattr(module, CLASS_FOR_STRUCTURE.get(width[1], ""), None)
            if declared_type is not wanted:
                _add(mismatches, "nested_type", structure=struct_name, field=name, path=path, provider_type=getattr(declared_type, "__name__", ""))
        if width is not None and width[0] == "primitive" and width[1] in AGGREGATE_TYPE:
            wanted = getattr(module, AGGREGATE_TYPE[width[1]], None)
            if declared_type is not wanted:
                _add(mismatches, "nested_type", structure=struct_name, field=name, path=path, provider_type=getattr(declared_type, "__name__", ""))
        if kind == "aggregate" and width is None:
            wanted_name = UNSIZED_AGGREGATE.get(name)
            wanted = None if wanted_name is None else getattr(module, wanted_name, None)
            if wanted is None or declared_type is not wanted:
                _add(mismatches, "nested_type", structure=struct_name, field=name, path=path)
        if sdk is not None and compare_offsets:
            sdk_offset, sdk_width, bound_path = expected[struct_name][sdk]
            if absolute != sdk_offset or actual_width != sdk_width:
                _add(
                    mismatches,
                    "layout_mismatch",
                    structure=struct_name,
                    field=sdk,
                    path=bound_path,
                    ctypes_offset=absolute,
                    sdk_offset=sdk_offset,
                    ctypes_width=actual_width,
                    sdk_width=sdk_width,
                )
            else:
                matched.append({
                    "structure": struct_name,
                    "field": sdk,
                    "path": bound_path,
                    "offset": sdk_offset,
                    "width": sdk_width,
                })
        elif width is not None:
            try:
                sdk_width = _resolve_width(abi, width)
            except LayoutMiss as exc:
                _add(mismatches, exc.kind, field=name, path=path, **exc.detail)
                sdk_width = None
            if sdk_width is not None and actual_width != sdk_width:
                _add(
                    mismatches,
                    "scalar_width_mismatch",
                    structure=struct_name,
                    field=name,
                    path=path,
                    ctypes_width=actual_width,
                    sdk_width=sdk_width,
                )
            elif sdk_width is not None and not compare_offsets:
                without_oracle.append({
                    "path": path,
                    "width": sdk_width,
                    "offset_compared": False,
                    "oracle_offset": None,
                })
            elif sdk_width is not None:
                width_only.append({
                    "path": path,
                    "width": sdk_width,
                    "offset_compared": False,
                    "oracle_offset": None,
                })
        elif not compare_offsets:
            without_oracle.append({
                "path": path,
                "width": actual_width,
                "offset_compared": False,
                "oracle": None,
                "oracle_offset": None,
            })
        elif kind == "aggregate":
            unmeasured.append({
                "path": path,
                "offset_compared": False,
                "width_compared": False,
                "oracle": None,
                "oracle_offset": None,
                "provider_type": getattr(declared_type, "__name__", ""),
            })
        if children and isinstance(declared_type, type) and issubclass(declared_type, (ctypes.Structure, ctypes.Union)):
            _walk(
                declared_type,
                children,
                absolute,
                struct_name,
                abi,
                expected,
                module,
                mismatches,
                visited,
                width_only,
                without_oracle,
                unmeasured,
                matched,
                compare_offsets,
                path,
            )
    for name in actual_names:
        if name not in spec_names:
            _add(mismatches, "unexpected_provider_field", structure=struct_name, field=name, type=cls.__name__)


def _compare_primitives(abi, module, ctypes_module, mismatches):
    table = abi["primitives"]
    compared = []
    for key, attr in DIRECT_PRIMITIVES.items():
        if key not in table:
            _add(mismatches, "missing_primitive", key=key)
            continue
        sdk_width = _layout_int(table[key])
        actual = ctypes_module.sizeof(getattr(ctypes_module, attr))
        if sdk_width is None or actual != sdk_width:
            _add(mismatches, "primitive_width", key=key, ctypes_width=actual, sdk_width=sdk_width)
        compared.append({"key": key, "width": sdk_width, "ctypes": attr})
    for key, class_name in PROVIDER_PRIMITIVES.items():
        if key not in table:
            _add(mismatches, "missing_primitive", key=key)
            continue
        sdk_width = _layout_int(table[key])
        actual = ctypes_module.sizeof(getattr(module, class_name))
        if sdk_width is None or actual != sdk_width:
            _add(mismatches, "primitive_width", key=key, ctypes_width=actual, sdk_width=sdk_width)
        compared.append({"key": key, "width": sdk_width, "provider_type": class_name})
    recorded = []
    known = set(DIRECT_PRIMITIVES) | set(PROVIDER_PRIMITIVES) | set(RECORDED_PRIMITIVES)
    for key in table:
        if key not in known:
            _add(mismatches, "unclassified_primitive", key=key)
        elif key in RECORDED_PRIMITIVES:
            recorded.append({"key": key, "width": table[key], "used_by_provider_field": False})
    rules = {
        "int": 4,
        "long": 4,
        "pointer": 8,
        "size_t": 8,
        "SIZE_T": 8,
        "long_long": 8,
    }
    for key, want in rules.items():
        got = table.get(key)
        if got != want:
            _add(mismatches, "llp64", key=key, sdk_width=got, required=want)
    if table.get("size_t") != table.get("SIZE_T"):
        _add(mismatches, "size_t_case_width", size_t=table.get("size_t"), SIZE_T=table.get("SIZE_T"))
    return compared, recorded


def _provider_types(module, ctypes_module):
    found = []
    for name, value in vars(module).items():
        if not isinstance(value, type):
            continue
        if value in (ctypes_module.Structure, ctypes_module.Union):
            continue
        if issubclass(value, (ctypes_module.Structure, ctypes_module.Union)):
            found.append(name)
    return found


def _expanded_requirement_names(spec):
    _record, _provider_type, _provider_fields, fields, sdk_only, _host, experiment, _primitive = spec
    names = [sdk for _provider, sdk, _width in fields]
    names.append("sizeof")
    names.extend(sdk_only)
    names.extend(experiment)
    return names


def _note_missing(bucket, structure, field):
    bucket.append({"structure": structure, "field": field})


def _experiment_value(key, value):
    if key in ("Linkage_mask", "Reserved2_mask"):
        if type(value) is not int or value < 0 or value > MEASUREMENT_UINT64:
            return None
        return value
    return _layout_int(value)


def _expanded_problem(item):
    if item.get("structure") in EXPANDED_RECORD_NAMES:
        return True
    kind = item.get("kind")
    if kind == "primitive_record_width":
        return True
    if kind in ("missing_provider_type", "not_structure") and item.get("type") in EXPANDED_PROVIDER_TYPES:
        return True
    return False


def _mask_beyond_span(mask, nbytes):
    """True when mask bits sit outside the measured container width.

    The SDK packs the experiment masks into the storage bytes, low byte first.
    A mask wider than that span is not a provider bit-field value.
    """
    if nbytes <= 0:
        return mask != 0
    if nbytes >= 8:
        return False
    return mask >> (nbytes * 8) != 0


def _span_outside_structure(storage, nbytes, limit):
    if type(limit) is not int:
        return True
    if nbytes > limit or storage > limit - nbytes:
        return True
    return False


def _linkage_descriptor(cls, actual, ctypes_module, mismatches, record):
    """Offset and sizeof-width of the provider's one opaque Linkage field.

    A descriptor size that disagrees with that width is its own mismatch.
    This does not split Linkage into two bit-fields.
    """
    if "Linkage" not in actual:
        return None, None
    descriptor = getattr(cls, "Linkage", None)
    offset = None if descriptor is None else _layout_int(_field_offset(descriptor))
    try:
        width = ctypes_module.sizeof(actual["Linkage"])
    except (TypeError, ValueError):
        width = None
    if type(width) is not int:
        width = None
    reported = None if descriptor is None else getattr(descriptor, "size", None)
    if reported is not None and _layout_int(reported) != width:
        _add(mismatches, "descriptor_width", structure=record, field="Linkage", path="Linkage")
    return offset, width


def _compare_linkage_span(record, parsed, cls, actual, ctypes_module, sdk_size, provider_ready, mismatches, experiments):
    """Compare the SDK container span with the opaque Linkage descriptor.

    Masks are recorded as SDK-only experiment values. They are not provider fields.
    """
    storage = parsed["Linkage_Reserved2_storage"]
    nbytes = parsed["Linkage_Reserved2_bytes"]
    linkage_mask = parsed["Linkage_mask"]
    reserved_mask = parsed["Reserved2_mask"]
    experiments.append({
        "structure": record,
        "Linkage_Reserved2_storage": storage,
        "Linkage_Reserved2_bytes": nbytes,
        "Linkage_mask": linkage_mask,
        "Reserved2_mask": reserved_mask,
        "provider_field": "Linkage",
        "provider_bitfields": False,
        "sdk_only": True,
    })
    if nbytes == 0:
        _add(mismatches, "experiment_span", structure=record, field="Linkage_Reserved2_bytes", reason="empty")
    limit = sdk_size
    if limit is None and provider_ready:
        try:
            limit = ctypes_module.sizeof(cls)
        except (TypeError, ValueError):
            limit = None
    if _span_outside_structure(storage, nbytes, limit):
        _add(mismatches, "experiment_span", structure=record, field="Linkage_Reserved2_storage", reason="out_of_bounds")
    if provider_ready:
        provider_offset, provider_width = _linkage_descriptor(cls, actual, ctypes_module, mismatches, record)
    else:
        provider_offset, provider_width = None, None
    if provider_offset is None or provider_width is None or provider_offset != storage or provider_width != nbytes:
        _add(
            mismatches,
            "experiment_span",
            structure=record,
            field="Linkage",
            reason="wrong",
            provider_offset=provider_offset,
            provider_width=provider_width,
        )
    if linkage_mask == 0 or reserved_mask == 0:
        _add(mismatches, "experiment_mask", structure=record, reason="zero")
    if linkage_mask & reserved_mask:
        _add(mismatches, "experiment_mask", structure=record, reason="overlap")
    if _mask_beyond_span(linkage_mask, nbytes) or _mask_beyond_span(reserved_mask, nbytes):
        _add(mismatches, "experiment_mask", structure=record, reason="beyond_span")


def _label_nested_notes(width_only, unmeasured, compared_pairs):
    """Move notes whose expanded record already compared the offset.

    A parent walk can still lack an offsetof key after the expanded record
    measured that field. Those notes must not stay in the unmeasured list.
    """
    nested = []
    kept_width = []
    kept_unmeasured = []
    for item in width_only:
        target = _NESTED_EXPANDED_FIELD.get(str(item.get("path", "")).rsplit(".", 1)[-1])
        if target in compared_pairs:
            item["offset_compared"] = True
            item["expanded_structure"] = target[0]
            item["expanded_field"] = target[1]
            item["nested_walk"] = "compared_on_expanded_record"
            nested.append(item)
        else:
            kept_width.append(item)
    for item in unmeasured:
        target = _NESTED_EXPANDED_FIELD.get(str(item.get("path", "")).rsplit(".", 1)[-1])
        if target in compared_pairs:
            item["offset_compared"] = True
            item["width_compared"] = True
            item["expanded_structure"] = target[0]
            item["expanded_field"] = target[1]
            item["nested_walk"] = "compared_on_expanded_record"
            nested.append(item)
        else:
            kept_unmeasured.append(item)
    return kept_width, kept_unmeasured, nested


def _bind_expanded_records(module, abi, ctypes_module, mismatches, matched, aliases):
    """Bind provider fields to expanded SDK names. Absent records stay missing.

    Numbers are read from the oracle object only. A missing record is not
    filled from ctypes.
    """
    required_missing = []
    oracle_backed = set()
    bound_records = []
    compared_pairs = []
    experiments = []
    for spec in EXPANDED_RECORDS:
        record, provider_type, provider_fields, fields, sdk_only, sdk_only_host, experiment, primitive_width = spec
        names = _expanded_requirement_names(spec)
        if record not in abi or type(abi.get(record)) is not dict:
            if record in abi:
                _add(mismatches, "bad_sdk_record", structure=record)
            for field in names:
                _note_missing(required_missing, record, field)
            continue
        block = abi[record]
        bound_records.append(record)
        oracle_backed.add(provider_type)
        allowed = {sdk for _provider, sdk, _width in fields}
        allowed.update(sdk_only)
        allowed.update(experiment)
        for field in sorted(set(block) - {"sizeof"} - allowed):
            _add(mismatches, "unclassified_sdk_field", structure=record, field=field)
        cls = getattr(module, provider_type, None)
        provider_ready = isinstance(cls, type) and issubclass(cls, ctypes_module.Structure) and not issubclass(cls, ctypes_module.Union)
        declared = []
        if not provider_ready:
            kind = "not_structure" if isinstance(cls, type) else "missing_provider_type"
            _add(mismatches, kind, type=provider_type, structure=record)
        else:
            try:
                declared = _declared_fields(cls)
            except LayoutMiss as exc:
                detail = {"structure": record}
                detail.update(exc.detail)
                if "type" not in detail:
                    detail["type"] = provider_type
                _add(mismatches, exc.kind, **detail)
                declared = []
            actual_names = [name for name, _declared in declared]
            if actual_names != list(provider_fields):
                _add(
                    mismatches,
                    "field_set",
                    structure=record,
                    type=provider_type,
                    provider=actual_names,
                    represented=list(provider_fields),
                )
        actual = {name: declared_type for name, declared_type in declared}
        host_range = None
        for provider_name, sdk_name, width in fields:
            if sdk_name not in block:
                _note_missing(required_missing, record, sdk_name)
                continue
            if record == "EVENT_HEADER_EXTENDED_DATA_ITEM":
                oracle_backed.add(provider_name)
            offset = _layout_int(block[sdk_name])
            try:
                sdk_width = _resolve_width(abi, width)
            except LayoutMiss as exc:
                if exc.kind in ("missing_structure", "missing_primitive"):
                    _note_missing(required_missing, record, sdk_name)
                else:
                    _add(mismatches, exc.kind, structure=record, field=sdk_name, **exc.detail)
                continue
            if offset is None or sdk_width is None:
                _add(mismatches, "bad_sdk_number", structure=record, field=sdk_name)
                continue
            compared_pairs.append((record, sdk_name))
            if sdk_name == sdk_only_host:
                host_range = (offset, offset + sdk_width)
            if provider_name not in actual:
                _add(mismatches, "missing_provider_field", structure=record, field=sdk_name, path=provider_name)
                continue
            descriptor = getattr(cls, provider_name, None)
            rel = None if descriptor is None else _layout_int(_field_offset(descriptor))
            try:
                actual_width = ctypes_module.sizeof(actual[provider_name])
            except (TypeError, ValueError):
                _add(mismatches, "width_unavailable", structure=record, field=sdk_name, path=provider_name)
                continue
            if type(actual_width) is not int or rel is None or rel != offset or actual_width != sdk_width:
                _add(
                    mismatches,
                    "layout_mismatch",
                    structure=record,
                    field=sdk_name,
                    path=provider_name,
                    ctypes_offset=rel,
                    sdk_offset=offset,
                    ctypes_width=actual_width,
                    sdk_width=sdk_width,
                )
                continue
            matched.append({
                "structure": record,
                "field": sdk_name,
                "path": provider_name,
                "offset": offset,
                "width": sdk_width,
            })
        if "sizeof" not in block:
            _note_missing(required_missing, record, "sizeof")
            sdk_size = None
        else:
            sdk_size = _layout_int(block.get("sizeof"))
            if sdk_size is None:
                _add(mismatches, "bad_sdk_number", structure=record, field="sizeof")
            elif provider_ready:
                try:
                    actual_size = ctypes_module.sizeof(cls)
                except (TypeError, ValueError):
                    _add(mismatches, "width_unavailable", structure=record, field="sizeof", type=provider_type)
                    actual_size = None
                if actual_size is not None and actual_size != sdk_size:
                    _add(mismatches, "structure_size", structure=record, ctypes_width=actual_size, sdk_width=sdk_size)
        for arm in sdk_only:
            if arm not in block:
                _note_missing(required_missing, record, arm)
                continue
            arm_offset = _layout_int(block[arm])
            if arm_offset is None:
                _add(mismatches, "bad_sdk_number", structure=record, field=arm)
                continue
            if host_range is not None and not (host_range[0] <= arm_offset < host_range[1]):
                _add(mismatches, "alias_not_overlay", structure=record, field=arm, offset=arm_offset)
                continue
            aliases.append({
                "structure": record,
                "field": arm,
                "offset": arm_offset,
                "represented": False,
            })
        parsed_experiment = {}
        for key in experiment:
            if key not in block:
                _note_missing(required_missing, record, key)
                continue
            value = _experiment_value(key, block[key])
            if value is None:
                _add(mismatches, "bad_sdk_number", structure=record, field=key)
                continue
            parsed_experiment[key] = value
        if experiment and set(parsed_experiment) == set(experiment):
            _compare_linkage_span(
                record,
                parsed_experiment,
                cls,
                actual,
                ctypes_module,
                sdk_size,
                provider_ready,
                mismatches,
                experiments,
            )
        if primitive_width and type(abi.get("primitives")) is dict and record in abi["primitives"] and "sizeof" in block:
            primitive = _layout_int(abi["primitives"].get(record))
            recorded = _layout_int(block.get("sizeof"))
            if primitive is None or recorded is None or primitive != recorded:
                _add(
                    mismatches,
                    "primitive_record_width",
                    structure=record,
                    primitive=primitive,
                    sizeof=recorded,
                )
    return required_missing, oracle_backed, bound_records, compared_pairs, experiments


def _coverage_flags(mismatches, required_missing):
    real = [item for item in mismatches if item.get("kind") != "omitted"]
    covered = len(real) == 0
    complete = not required_missing and not any(_expanded_problem(item) for item in real)
    return real, covered, complete


def compare_layouts(module, abi, ctypes_module):
    mismatches = []
    top = set(abi)
    want = {"schema", "arch", "primitives", *NINE}
    allowed_top = want | EXPANDED_RECORD_NAMES
    for key in sorted(want - top):
        _add(mismatches, "missing_required_data", key=key)
    for key in sorted(top - allowed_top):
        _add(mismatches, "unexpected_sdk_key", key=key)
    if abi.get("schema") != 1:
        _add(mismatches, "schema", value=abi.get("schema"))
    if type(abi.get("primitives")) is not dict:
        _add(mismatches, "missing_required_data", key="primitives")
        required_missing = []
        for spec in EXPANDED_RECORDS:
            record = spec[0]
            if type(abi.get(record)) is not dict:
                for field in _expanded_requirement_names(spec):
                    _note_missing(required_missing, record, field)
        real = [item for item in mismatches if item.get("kind") != "omitted"]
        return {
            "mismatches": real,
            "mismatches_omitted": 0,
            "covered_field_match": False,
            "complete_coverage": False,
            "required_missing_layouts": required_missing,
            "unmeasured": [],
            "nested_walk": [],
            "sdk_only_experiments": [],
            "coverage": {
                "complete": False,
                "structures": [],
                "sdk_fields_compared": 0,
                "sdk_fields_matched": 0,
                "sdk_only_experiments": 0,
            },
        }
    try:
        expected, ranges = _expected_map(abi)
    except LayoutMiss as exc:
        _add(mismatches, exc.kind, **exc.detail)
        expected, ranges = {}, {name: [] for name in NINE}
    aliases = _classify_sdk_fields(abi, expected, ranges, mismatches) if expected else []
    visited = set()
    width_only = []
    without_oracle = []
    unmeasured = []
    matched = []
    if expected:
        for struct_name, class_name, fields in STRUCTURES:
            cls = getattr(module, class_name, None)
            if not isinstance(cls, type):
                _add(mismatches, "missing_provider_type", type=class_name)
                continue
            try:
                _walk(
                    cls,
                    fields,
                    0,
                    struct_name,
                    abi,
                    expected,
                    module,
                    mismatches,
                    visited,
                    width_only,
                    without_oracle,
                    unmeasured,
                    matched,
                    True,
                    "",
                )
                actual_size = ctypes_module.sizeof(cls)
                sdk_size = _layout_int(abi[struct_name].get("sizeof"))
                if sdk_size is None or actual_size != sdk_size:
                    _add(mismatches, "structure_size", structure=struct_name, ctypes_width=actual_size, sdk_width=sdk_size)
            except LayoutMiss as exc:
                _add(mismatches, exc.kind, **exc.detail)
        extended = getattr(module, "_EVENT_HEADER_EXTENDED_DATA_ITEM", None)
        extended_width = None
        if not isinstance(extended, type):
            _add(mismatches, "missing_provider_type", type="_EVENT_HEADER_EXTENDED_DATA_ITEM")
        else:
            if not issubclass(extended, ctypes_module.Structure) or issubclass(extended, ctypes_module.Union):
                _add(mismatches, "not_structure", type="_EVENT_HEADER_EXTENDED_DATA_ITEM")
            try:
                _walk(
                    extended,
                    EXTENDED_FIELDS,
                    0,
                    "_EVENT_HEADER_EXTENDED_DATA_ITEM",
                    abi,
                    expected,
                    module,
                    mismatches,
                    visited,
                    width_only,
                    without_oracle,
                    unmeasured,
                    matched,
                    False,
                    "",
                )
                extended_width = ctypes_module.sizeof(extended)
            except LayoutMiss as exc:
                _add(mismatches, exc.kind, **exc.detail)
        extended_record = abi.get("EVENT_HEADER_EXTENDED_DATA_ITEM")
        if type(extended_record) is not dict and not any(
            item.get("path") == "_EVENT_HEADER_EXTENDED_DATA_ITEM" for item in without_oracle
        ):
            without_oracle.append({
                "path": "_EVENT_HEADER_EXTENDED_DATA_ITEM",
                "width": extended_width,
                "offset_compared": False,
                "oracle": None,
                "oracle_offset": None,
                "sdk_sizeof": None,
                "required_layout": True,
                "provider_use": "array_stride",
            })
        for item in without_oracle:
            use = EXTENDED_PROVIDER_USE.get(item.get("path"))
            if use is None:
                continue
            item["provider_use"] = use
            # Linkage is a ctypes USHORT standing in for the SDK bit-field.
            # The oracle does not emit offsetof(Linkage) or offsetof(Reserved2).
            if item.get("path") == "Linkage":
                item["required_layout"] = False
                item["sdk_offset"] = None
                continue
            item["required_layout"] = True
            item["sdk_offset"] = None
        matched_ids = {(item["structure"], item["field"]) for item in matched}
        for struct_name, fields_map in expected.items():
            for sdk in fields_map:
                if (struct_name, sdk) in matched_ids:
                    continue
                if any(item.get("structure") == struct_name and item.get("field") == sdk for item in mismatches):
                    continue
                _add(mismatches, "sdk_field_not_compared", structure=struct_name, field=sdk)
        provider_types = set(_provider_types(module, ctypes_module))
        for name in sorted(provider_types - visited):
            _add(mismatches, "unvisited_provider_type", type=name)
        for name in sorted(visited - provider_types):
            _add(mismatches, "visited_unknown_type", type=name)
    primitives, recorded = _compare_primitives(abi, module, ctypes_module, mismatches)
    required_missing, oracle_backed, bound_records, compared_pairs, experiments = _bind_expanded_records(
        module, abi, ctypes_module, mismatches, matched, aliases
    )
    if oracle_backed:
        without_oracle = [item for item in without_oracle if item.get("path") not in oracle_backed]
    if experiments:
        for item in without_oracle:
            if item.get("path") != "Linkage":
                continue
            # The container span was compared. There is still no offsetof(Linkage).
            item["offset_compared"] = True
            item["container"] = "Linkage_Reserved2_storage"
            item["provider_bitfields"] = False
            item["sdk_bitfields"] = "sdk_only_experiment"
            item["sdk_offset"] = None
    compared = set(compared_pairs)
    width_only, unmeasured, nested_walk = _label_nested_notes(width_only, unmeasured, compared)
    structures = list(NINE) if expected else []
    structures.extend(bound_records)
    nine_compared = sum(len(expected.get(name, {})) for name in NINE) if expected else 0
    real, covered_field_match, complete_coverage = _coverage_flags(mismatches, required_missing)
    omitted = next((int(item.get("count", 0)) for item in mismatches if item.get("kind") == "omitted"), 0)
    return {
        "structure_sizes": {
            name: abi[name]["sizeof"]
            for name in structures
            if name in abi and type(abi[name]) is dict and _layout_int(abi[name].get("sizeof")) is not None
        },
        "fields": matched[:200],
        "sdk_only_aliases": aliases,
        "sdk_only_experiments": experiments,
        "primitives_compared": primitives,
        "primitives_not_used_by_provider": recorded,
        "width_only_no_oracle_offset": width_only[:64],
        "provider_fields_without_oracle_record": without_oracle[:64],
        "unmeasured": unmeasured,
        "nested_walk": nested_walk[:64],
        "required_missing_layouts": required_missing,
        "covered_field_match": covered_field_match,
        "complete_coverage": complete_coverage,
        "coverage": {
            "structures": structures,
            "sdk_fields_compared": nine_compared + len(compared_pairs),
            "sdk_fields_matched": len(matched),
            "sdk_only_aliases": len(aliases),
            "sdk_only_experiments": len(experiments),
            "scalar_primitives_compared": len(primitives),
            "provider_types_visited": sorted(visited),
        },
        "mismatches": real,
        "mismatches_omitted": omitted,
    }


def _pe_machine(path: Path):
    handle = path.open("rb")
    try:
        header = handle.read(64)
        if len(header) < 64 or header[:2] != b"MZ":
            raise LayoutMiss("python_pe")
        e_lfanew = int.from_bytes(header[0x3C:0x40], "little")
        if e_lfanew < 64 or e_lfanew > 1024 * 1024:
            raise LayoutMiss("python_pe")
        handle.seek(e_lfanew)
        pe = handle.read(6)
    finally:
        handle.close()
    if len(pe) < 6 or pe[:4] != b"PE\0\0":
        raise LayoutMiss("python_pe")
    return int.from_bytes(pe[4:6], "little")


def _arch_gate(arch):
    info = {
        "intended_arch": arch,
        "platform_machine": platform.machine(),
        "pe_machine": None,
        "runner_arch": os.environ.get("RUNNER_ARCH"),
        "python_version": sys.version.split()[0],
    }
    problems = []
    try:
        info["pe_machine"] = _pe_machine(Path(sys.executable))
    except (OSError, LayoutMiss):
        problems.append({"kind": "python_pe"})
    if info["pe_machine"] != PE_MACHINE[arch]:
        problems.append({"kind": "python_arch_mismatch", "pe_machine": info["pe_machine"], "required": PE_MACHINE[arch]})
    if info["platform_machine"] != PLATFORM_MACHINE[arch]:
        problems.append({"kind": "platform_machine_mismatch", "platform_machine": info["platform_machine"]})
    runner = info["runner_arch"]
    if runner is not None and runner != RUNNER_ARCH[arch]:
        problems.append({"kind": "runner_arch_mismatch", "runner_arch": runner, "required": RUNNER_ARCH[arch]})
    return info, problems


def _refuse_libraries():
    import ctypes

    state = {"count": 0}

    def refuse(*_args, **_kwargs):
        state["count"] += 1
        raise RuntimeError("native_library_load_refused")

    ctypes.CDLL = refuse
    ctypes.WinDLL = refuse
    ctypes.OleDLL = refuse
    ctypes.PyDLL = refuse
    for name in ("cdll", "windll", "oledll", "pydll"):
        loader = getattr(ctypes, name, None)
        if loader is not None and hasattr(loader, "_dlltype"):
            loader._dlltype = refuse
    return state


def _oracle_binding(oracle: Path, arch: str):
    manifest_path = oracle / "manifest.json"
    files = {
        "x64": {
            "abi": oracle / "x64" / "abi.json",
            "metadata": oracle / "x64" / "metadata.json",
        },
        "arm64": {
            "abi": oracle / "arm64" / "abi.json",
            "metadata": oracle / "arm64" / "metadata.json",
        },
    }
    for group in files.values():
        for path in group.values():
            if not path.is_file():
                raise LayoutMiss("oracle_missing", name=str(path.name))
    if not manifest_path.is_file():
        raise LayoutMiss("oracle_missing", name="manifest.json")
    manifest = _load_json(manifest_path, 8192)
    if manifest.get("source") != ORACLE_SOURCE or manifest.get("run") != ORACLE_RUN:
        raise LayoutMiss("oracle_provenance")
    if manifest.get("trace_started") is not False:
        raise LayoutMiss("oracle_trace_flag")
    listed = manifest.get("files")
    if type(listed) is not list or len(listed) != 4:
        raise LayoutMiss("oracle_manifest_files")
    hashes = {}
    for arch_name, group in files.items():
        hashes[arch_name] = {
            "abi_sha256": _sha256(group["abi"], 16384),
            "metadata_sha256": _sha256(group["metadata"], 4096),
        }
    expected = {
        "x64/abi.json": hashes["x64"]["abi_sha256"],
        "x64/metadata.json": hashes["x64"]["metadata_sha256"],
        "arm64/abi.json": hashes["arm64"]["abi_sha256"],
        "arm64/metadata.json": hashes["arm64"]["metadata_sha256"],
    }
    seen_paths = []
    for item in listed:
        item_path = item.get("path") if type(item) is dict else None
        if item_path not in expected or item_path in seen_paths:
            raise LayoutMiss("oracle_manifest_files")
        seen_paths.append(item_path)
        if item.get("sha256") != expected[item_path]:
            raise LayoutMiss("oracle_hash_mismatch", path=item_path)
    if set(seen_paths) != set(expected):
        raise LayoutMiss("oracle_manifest_files")
    abi = _load_json(files[arch]["abi"], 16384)
    metadata = _load_json(files[arch]["metadata"], 4096)
    other = "arm64" if arch == "x64" else "x64"
    other_abi = _load_json(files[other]["abi"], 16384)
    other_metadata = _load_json(files[other]["metadata"], 4096)
    if abi.get("arch") != ORACLE_ARCH[arch] or other_abi.get("arch") != ORACLE_ARCH[other]:
        raise LayoutMiss("oracle_arch")
    for name, body in ((arch, metadata), (other, other_metadata)):
        if body.get("host_arch") != name or body.get("target_arch") != name:
            raise LayoutMiss("metadata_arch", arch=name)
        if body.get("windows_sdk_version") != SDK_VERSION:
            raise LayoutMiss("metadata_sdk", arch=name)
        if body.get("pe_machine") != PE_MACHINE[name]:
            raise LayoutMiss("metadata_pe", arch=name)
        if body.get("abi_bytes") != (files[name]["abi"]).stat().st_size:
            raise LayoutMiss("metadata_abi_bytes", arch=name)
    return {
        "manifest_sha256": _sha256(manifest_path, 8192),
        "source": manifest["source"],
        "run": manifest["run"],
        "trace_started": False,
        "hashes": hashes,
        "abi": abi,
        "metadata": metadata,
        "other_metadata": other_metadata,
        "other_arch": other,
    }


def _receipt(path: Path, payload: dict):
    if path.suffix.lower() != ".json":
        raise LayoutMiss("receipt_path")
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if len(text.encode("utf-8")) > 256_000:
        raise LayoutMiss("receipt_too_large")
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


def _base_receipt(arch_info, binding, provider_sha, loads, native_api_loaded, comparison_ran):
    metadata = {
        "host": arch_info,
        "interpreter_note": "CPython ctypes binds kernel32.GetLastError during ctypes import. This check refuses later native library construction and does not call ETW.",
        "provider_import_library_loads": None if loads is None else loads,
        "native_api_loaded": native_api_loaded,
        "provider_sha256": provider_sha,
        "oracle": None,
    }
    if binding is not None:
        metadata["oracle"] = {
            "source": binding["source"],
            "run": binding["run"],
            "trace_started": False,
            "manifest_sha256": binding["manifest_sha256"],
            "sdk_version": SDK_VERSION,
            "compared_arch": arch_info.get("intended_arch"),
            "hash_only_arch": binding["other_arch"],
            "files": binding["hashes"],
            "compared_metadata": binding["metadata"],
            "hash_only_metadata": binding["other_metadata"],
        }
    return {
        "schema": 1,
        "check": CHECK,
        "declaration_match": False,
        "comparison_ran": comparison_ran,
        "production_ready": False,
        "native_tracing": False,
        "native_emission": False,
        "resource_acceptance": False,
        "cpu_acceptance": False,
        "ram_acceptance": False,
        "numeric": None,
        "metadata": metadata,
    }


def _read_provider_source(path: Path) -> bytes:
    handle = path.open("rb")
    try:
        data = handle.read(PROVIDER_SOURCE_LIMIT + 1)
    finally:
        handle.close()
    if len(data) > PROVIDER_SOURCE_LIMIT:
        raise LayoutMiss("provider_too_large", bytes=len(data), limit=PROVIDER_SOURCE_LIMIT)
    return data


def _execute_provider_source(path: Path, source: bytes):
    module = types.ModuleType(PROVIDER_MODULE)
    module.__file__ = str(path)
    module.__package__ = "deploy"
    # Class statements resolve the defining module through sys.modules.
    previous = sys.modules.get(PROVIDER_MODULE)
    sys.modules[PROVIDER_MODULE] = module
    try:
        code = compile(source, str(path), "exec")
        exec(code, module.__dict__)
    finally:
        if previous is None:
            sys.modules.pop(PROVIDER_MODULE, None)
        else:
            sys.modules[PROVIDER_MODULE] = previous
    return module


def main(argv=None):
    parser = argparse.ArgumentParser(description="Compare ETW ctypes declarations to the frozen SDK oracle.")
    parser.add_argument("--arch", required=True, choices=ARCHES)
    parser.add_argument("--receipt", required=True)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    oracle = Path(__file__).resolve().parent / "oracle"
    receipt_path = Path(args.receipt)
    if not receipt_path.is_absolute():
        receipt_path = Path.cwd() / receipt_path
    receipt_path = receipt_path.resolve()
    if oracle.resolve() == receipt_path or oracle.resolve() in receipt_path.parents:
        print("receipt_path_overlaps_oracle", file=sys.stderr)
        return 1
    arch_info, arch_problems = _arch_gate(args.arch)
    binding = None
    oracle_problem = None
    try:
        binding = _oracle_binding(oracle, args.arch)
    except LayoutMiss as exc:
        oracle_problem = {"kind": exc.kind, **exc.detail}
    if arch_problems or oracle_problem is not None:
        payload = _base_receipt(arch_info, binding, None, None, None, False)
        payload["numeric"] = {"mismatches": arch_problems + ([oracle_problem] if oracle_problem else [])}
        _receipt(receipt_path, payload)
        print("declaration_match=false", file=sys.stderr)
        return 1

    sys.dont_write_bytecode = True
    loads = _refuse_libraries()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    expected_provider = (root / "deploy" / "owned_launch_windows_etw.py").resolve()
    if PROVIDER_MODULE in sys.modules:
        payload = _base_receipt(arch_info, binding, None, loads["count"], None, False)
        payload["numeric"] = {"mismatches": [{"kind": "provider_already_imported"}]}
        _receipt(receipt_path, payload)
        return 1
    if not expected_provider.is_file():
        payload = _base_receipt(arch_info, binding, None, loads["count"], None, False)
        payload["numeric"] = {"mismatches": [{"kind": "provider_path"}]}
        _receipt(receipt_path, payload)
        print("declaration_match=false", file=sys.stderr)
        return 1
    try:
        source = _read_provider_source(expected_provider)
    except LayoutMiss as exc:
        payload = _base_receipt(arch_info, binding, None, loads["count"], None, False)
        payload["numeric"] = {"mismatches": [{"kind": exc.kind, **exc.detail}]}
        _receipt(receipt_path, payload)
        print("declaration_match=false", file=sys.stderr)
        return 1
    except OSError as exc:
        payload = _base_receipt(arch_info, binding, None, loads["count"], None, False)
        payload["numeric"] = {"mismatches": [{"kind": "provider_import_failed", "error": type(exc).__name__}]}
        _receipt(receipt_path, payload)
        print("declaration_match=false", file=sys.stderr)
        return 1
    provider_sha = hashlib.sha256(source).hexdigest()
    try:
        module = _execute_provider_source(expected_provider, source)
    except Exception as exc:
        kind = "native_library_load_refused" if loads["count"] else "provider_import_failed"
        payload = _base_receipt(arch_info, binding, provider_sha, loads["count"], None, False)
        payload["numeric"] = {"mismatches": [{"kind": kind, "error": type(exc).__name__}]}
        _receipt(receipt_path, payload)
        print("declaration_match=false", file=sys.stderr)
        return 1
    native_api_loaded = getattr(module, "native_api_loaded", None)
    import_problems = []
    if module.__name__ != PROVIDER_MODULE or module.__package__ != "deploy":
        import_problems.append({"kind": "provider_module_identity"})
    if Path(module.__file__).resolve() != expected_provider:
        import_problems.append({"kind": "provider_path"})
    if loads["count"] != 0:
        import_problems.append({"kind": "native_library_load_refused", "count": loads["count"]})
    if native_api_loaded is not False:
        import_problems.append({"kind": "native_api_loaded", "value": native_api_loaded is True})
    if import_problems:
        loaded_flag = native_api_loaded if type(native_api_loaded) is bool else None
        payload = _base_receipt(arch_info, binding, provider_sha, loads["count"], loaded_flag, False)
        payload["numeric"] = {"mismatches": import_problems}
        _receipt(receipt_path, payload)
        print("declaration_match=false", file=sys.stderr)
        return 1

    import ctypes

    numeric = compare_layouts(module, binding["abi"], ctypes)
    match = numeric.get("covered_field_match") is True and numeric.get("complete_coverage") is True
    payload = _base_receipt(arch_info, binding, provider_sha, loads["count"], False, True)
    payload["declaration_match"] = match
    payload["numeric"] = numeric
    _receipt(receipt_path, payload)
    print("declaration_match=" + ("true" if match else "false"))
    return 0 if match else 1


if __name__ == "__main__":
    sys.exit(main())
