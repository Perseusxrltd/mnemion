/* SDK ABI oracle. Prints sizeof/offsetof for the Windows headers.
   Linkage and Reserved2 are a nameless USHORT bit-field. Their span and
   masks come from one zeroed object. Those numbers are not offsetof.
   It does not call StartTrace, OpenTrace, ProcessTrace, StopTrace, or CloseTrace.
   x64 and ARM64 only. MSVC nameless unions are required. */

#if !defined(_MSC_VER)
#error This ABI oracle compiles only with MSVC against the Windows SDK.
#endif
#if defined(_M_ARM64EC) || defined(_M_HYBRID_X86_ARM64) || defined(_M_IX86) || defined(_M_ARM)
#error Unsupported architecture. This ABI oracle supports only x64 and ARM64.
#elif defined(_M_X64) && defined(_M_ARM64)
#error Unsupported architecture. x64 and ARM64 are both defined.
#elif defined(_M_X64)
#define ABI_ARCH 1
#elif defined(_M_ARM64)
#define ABI_ARCH 2
#else
#error Unsupported architecture. This ABI oracle supports only x64 and ARM64.
#endif
#if defined(NONAMELESSUNION) || !defined(_MSC_EXTENSIONS)
#error This ABI oracle needs MSVC nameless unions to measure the SDK members.
#endif

#if defined(_MSC_VER)
#pragma warning(push, 0)
#endif
#include <windows.h>
#include <evntcons.h>
#if defined(_MSC_VER)
#pragma warning(pop)
#endif

#include <limits.h>
#include <stdarg.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

_Static_assert(sizeof(void *) == 8, "LLP64 pointer width");
_Static_assert(sizeof(int) == 4, "LLP64 int width");
_Static_assert(sizeof(long) == 4, "LLP64 long width");
_Static_assert(sizeof(long long) == 8, "LLP64 long long width");

#define ABI_JSON_MAX 16384

static char g_out[ABI_JSON_MAX];
static size_t g_len;
static int g_depth;
static int g_first[8];

static void fail_bound(void) {
    fputs("{\"error\":1}\n", stdout);
    exit(3);
}

static void appendf(const char *fmt, ...) {
    char line[512];
    va_list args;
    int wrote;

    va_start(args, fmt);
    wrote = vsnprintf(line, sizeof line, fmt, args);
    va_end(args);
    if (wrote < 0 || (size_t)wrote >= sizeof line || g_len + (size_t)wrote >= ABI_JSON_MAX) {
        fail_bound();
    }
    memcpy(g_out + g_len, line, (size_t)wrote);
    g_len += (size_t)wrote;
}

static void push_object(const char *name) {
    if (g_depth >= (int)(sizeof g_first / sizeof g_first[0])) {
        fail_bound();
    }
    if (g_depth > 0 && !g_first[g_depth - 1]) {
        appendf(",");
    }
    if (g_depth > 0) {
        g_first[g_depth - 1] = 0;
    }
    if (name != NULL) {
        appendf("\"%s\":{", name);
    } else {
        appendf("{");
    }
    g_first[g_depth] = 1;
    g_depth += 1;
}

static void pop_object(void) {
    g_depth -= 1;
    appendf("}");
}

static void num(const char *key, unsigned long long value) {
    if (!g_first[g_depth - 1]) {
        appendf(",");
    }
    g_first[g_depth - 1] = 0;
    appendf("\"%s\":%llu", key, value);
}

static void size_of(const char *key, size_t value) {
    num(key, (unsigned long long)value);
}

#define OFF(type, member, key) num((key), (unsigned long long)offsetof(type, member))

static void fail_bitfield(void) {
    fputs("EVENT_HEADER_EXTENDED_DATA_ITEM bitfield storage is not one disjoint span\n", stderr);
    exit(3);
}

static void read_bytes(const void *from, unsigned char *to, size_t size) {
    const volatile unsigned char *src = (const volatile unsigned char *)from;
    size_t index;

    for (index = 0; index < size; index++) {
        to[index] = src[index];
    }
}

static int span_clean(const unsigned char *diff, size_t origin, size_t width, size_t size) {
    size_t index;

    if (width > size || origin > size - width) {
        return 0;
    }
    for (index = origin; index < origin + width; index++) {
        if (diff[index] != 0) {
            return 0;
        }
    }
    return 1;
}

/* The all-ones value is volatile so a constant overflow is not diagnosed.
   USHORT bit-fields are an SDK extension. Assigning all-ones lets the
   compiler keep only the bits the field can hold. */
static void extended_bitfield(size_t *origin, size_t *width,
                              unsigned long long *linkage_mask,
                              unsigned long long *reserved_mask) {
    EVENT_HEADER_EXTENDED_DATA_ITEM cleared;
    EVENT_HEADER_EXTENDED_DATA_ITEM linkage_item;
    EVENT_HEADER_EXTENDED_DATA_ITEM reserved_item;
    unsigned char base[sizeof(EVENT_HEADER_EXTENDED_DATA_ITEM)];
    unsigned char linkage_bytes[sizeof(EVENT_HEADER_EXTENDED_DATA_ITEM)];
    unsigned char reserved_bytes[sizeof(EVENT_HEADER_EXTENDED_DATA_ITEM)];
    unsigned char linkage_diff[sizeof(EVENT_HEADER_EXTENDED_DATA_ITEM)];
    unsigned char reserved_diff[sizeof(EVENT_HEADER_EXTENDED_DATA_ITEM)];
    volatile USHORT ones = USHRT_MAX;
    size_t size = sizeof(EVENT_HEADER_EXTENDED_DATA_ITEM);
    size_t index;
    size_t first;
    size_t last;
    unsigned long long link_bits = 0;
    unsigned long long reserved_bits = 0;

    memset(&cleared, 0, size);
    linkage_item = cleared;
    reserved_item = cleared;
    linkage_item.Linkage = ones;
    reserved_item.Reserved2 = ones;
    read_bytes(&cleared, base, size);
    read_bytes(&linkage_item, linkage_bytes, size);
    read_bytes(&reserved_item, reserved_bytes, size);
    for (index = 0; index < size; index++) {
        linkage_diff[index] = (unsigned char)(base[index] ^ linkage_bytes[index]);
        reserved_diff[index] = (unsigned char)(base[index] ^ reserved_bytes[index]);
    }
    if (!span_clean(linkage_diff, offsetof(EVENT_HEADER_EXTENDED_DATA_ITEM, Reserved1), sizeof(cleared.Reserved1), size) ||
        !span_clean(reserved_diff, offsetof(EVENT_HEADER_EXTENDED_DATA_ITEM, Reserved1), sizeof(cleared.Reserved1), size) ||
        !span_clean(linkage_diff, offsetof(EVENT_HEADER_EXTENDED_DATA_ITEM, ExtType), sizeof(cleared.ExtType), size) ||
        !span_clean(reserved_diff, offsetof(EVENT_HEADER_EXTENDED_DATA_ITEM, ExtType), sizeof(cleared.ExtType), size) ||
        !span_clean(linkage_diff, offsetof(EVENT_HEADER_EXTENDED_DATA_ITEM, DataSize), sizeof(cleared.DataSize), size) ||
        !span_clean(reserved_diff, offsetof(EVENT_HEADER_EXTENDED_DATA_ITEM, DataSize), sizeof(cleared.DataSize), size) ||
        !span_clean(linkage_diff, offsetof(EVENT_HEADER_EXTENDED_DATA_ITEM, DataPtr), sizeof(cleared.DataPtr), size) ||
        !span_clean(reserved_diff, offsetof(EVENT_HEADER_EXTENDED_DATA_ITEM, DataPtr), sizeof(cleared.DataPtr), size)) {
        fail_bitfield();
    }
    first = size;
    last = 0;
    for (index = 0; index < size; index++) {
        if (linkage_diff[index] != 0 || reserved_diff[index] != 0) {
            if (first == size) {
                first = index;
            }
            last = index;
        }
    }
    if (first == size || (last - first) > 7) {
        fail_bitfield();
    }
    for (index = first; index <= last; index++) {
        unsigned shift = (unsigned)((index - first) * 8);

        if ((linkage_diff[index] | reserved_diff[index]) == 0 ||
            (linkage_diff[index] & reserved_diff[index]) != 0) {
            fail_bitfield();
        }
        link_bits |= (unsigned long long)linkage_diff[index] << shift;
        reserved_bits |= (unsigned long long)reserved_diff[index] << shift;
    }
    if (link_bits == 0 || reserved_bits == 0) {
        fail_bitfield();
    }
    *origin = first;
    *width = last - first + 1;
    *linkage_mask = link_bits;
    *reserved_mask = reserved_bits;
}

static void primitives(void) {
    push_object("primitives");
    size_of("char", sizeof(char));
    size_of("short", sizeof(short));
    size_of("int", sizeof(int));
    size_of("long", sizeof(long));
    size_of("long_long", sizeof(long long));
    size_of("pointer", sizeof(void *));
    size_of("wchar_t", sizeof(wchar_t));
    size_of("size_t", sizeof(size_t));
    size_of("ptrdiff_t", sizeof(ptrdiff_t));
    size_of("uintptr_t", sizeof(uintptr_t));
    size_of("int32_t", sizeof(int32_t));
    size_of("int64_t", sizeof(int64_t));
    size_of("UCHAR", sizeof(UCHAR));
    size_of("USHORT", sizeof(USHORT));
    size_of("ULONG", sizeof(ULONG));
    size_of("BOOL", sizeof(BOOL));
    size_of("BOOLEAN", sizeof(BOOLEAN));
    size_of("WCHAR", sizeof(WCHAR));
    size_of("HANDLE", sizeof(HANDLE));
    size_of("SIZE_T", sizeof(SIZE_T));
    size_of("ULONG_PTR", sizeof(ULONG_PTR));
    size_of("LONGLONG", sizeof(LONGLONG));
    size_of("ULONGLONG", sizeof(ULONGLONG));
    size_of("LARGE_INTEGER", sizeof(LARGE_INTEGER));
    size_of("GUID", sizeof(GUID));
    size_of("TIME_ZONE_INFORMATION", sizeof(TIME_ZONE_INFORMATION));
    size_of("ETW_BUFFER_CONTEXT", sizeof(ETW_BUFFER_CONTEXT));
    pop_object();
}

static void wnode_header(void) {
    push_object("WNODE_HEADER");
    size_of("sizeof", sizeof(WNODE_HEADER));
    OFF(WNODE_HEADER, BufferSize, "BufferSize");
    OFF(WNODE_HEADER, ProviderId, "ProviderId");
    OFF(WNODE_HEADER, HistoricalContext, "HistoricalContext");
    OFF(WNODE_HEADER, Version, "Version");
    OFF(WNODE_HEADER, Linkage, "Linkage");
    OFF(WNODE_HEADER, CountLost, "CountLost");
    OFF(WNODE_HEADER, KernelHandle, "KernelHandle");
    OFF(WNODE_HEADER, TimeStamp, "TimeStamp");
    OFF(WNODE_HEADER, Guid, "Guid");
    OFF(WNODE_HEADER, ClientContext, "ClientContext");
    OFF(WNODE_HEADER, Flags, "Flags");
    pop_object();
}

static void event_trace_properties(void) {
    push_object("EVENT_TRACE_PROPERTIES");
    size_of("sizeof", sizeof(EVENT_TRACE_PROPERTIES));
    OFF(EVENT_TRACE_PROPERTIES, Wnode, "Wnode");
    OFF(EVENT_TRACE_PROPERTIES, BufferSize, "BufferSize");
    OFF(EVENT_TRACE_PROPERTIES, MinimumBuffers, "MinimumBuffers");
    OFF(EVENT_TRACE_PROPERTIES, MaximumBuffers, "MaximumBuffers");
    OFF(EVENT_TRACE_PROPERTIES, MaximumFileSize, "MaximumFileSize");
    OFF(EVENT_TRACE_PROPERTIES, LogFileMode, "LogFileMode");
    OFF(EVENT_TRACE_PROPERTIES, FlushTimer, "FlushTimer");
    OFF(EVENT_TRACE_PROPERTIES, EnableFlags, "EnableFlags");
    OFF(EVENT_TRACE_PROPERTIES, AgeLimit, "AgeLimit");
    OFF(EVENT_TRACE_PROPERTIES, FlushThreshold, "FlushThreshold");
    OFF(EVENT_TRACE_PROPERTIES, NumberOfBuffers, "NumberOfBuffers");
    OFF(EVENT_TRACE_PROPERTIES, FreeBuffers, "FreeBuffers");
    OFF(EVENT_TRACE_PROPERTIES, EventsLost, "EventsLost");
    OFF(EVENT_TRACE_PROPERTIES, BuffersWritten, "BuffersWritten");
    OFF(EVENT_TRACE_PROPERTIES, LogBuffersLost, "LogBuffersLost");
    OFF(EVENT_TRACE_PROPERTIES, RealTimeBuffersLost, "RealTimeBuffersLost");
    OFF(EVENT_TRACE_PROPERTIES, LoggerThreadId, "LoggerThreadId");
    OFF(EVENT_TRACE_PROPERTIES, LogFileNameOffset, "LogFileNameOffset");
    OFF(EVENT_TRACE_PROPERTIES, LoggerNameOffset, "LoggerNameOffset");
    pop_object();
}

static void event_descriptor(void) {
    push_object("EVENT_DESCRIPTOR");
    size_of("sizeof", sizeof(EVENT_DESCRIPTOR));
    OFF(EVENT_DESCRIPTOR, Id, "Id");
    OFF(EVENT_DESCRIPTOR, Version, "Version");
    OFF(EVENT_DESCRIPTOR, Channel, "Channel");
    OFF(EVENT_DESCRIPTOR, Level, "Level");
    OFF(EVENT_DESCRIPTOR, Opcode, "Opcode");
    OFF(EVENT_DESCRIPTOR, Task, "Task");
    OFF(EVENT_DESCRIPTOR, Keyword, "Keyword");
    pop_object();
}

static void event_header(void) {
    push_object("EVENT_HEADER");
    size_of("sizeof", sizeof(EVENT_HEADER));
    OFF(EVENT_HEADER, Size, "Size");
    OFF(EVENT_HEADER, HeaderType, "HeaderType");
    OFF(EVENT_HEADER, Flags, "Flags");
    OFF(EVENT_HEADER, EventProperty, "EventProperty");
    OFF(EVENT_HEADER, ThreadId, "ThreadId");
    OFF(EVENT_HEADER, ProcessId, "ProcessId");
    OFF(EVENT_HEADER, TimeStamp, "TimeStamp");
    OFF(EVENT_HEADER, ProviderId, "ProviderId");
    OFF(EVENT_HEADER, EventDescriptor, "EventDescriptor");
    OFF(EVENT_HEADER, KernelTime, "KernelTime");
    OFF(EVENT_HEADER, UserTime, "UserTime");
    OFF(EVENT_HEADER, ProcessorTime, "ProcessorTime");
    OFF(EVENT_HEADER, ActivityId, "ActivityId");
    pop_object();
}

static void event_record(void) {
    push_object("EVENT_RECORD");
    size_of("sizeof", sizeof(EVENT_RECORD));
    OFF(EVENT_RECORD, EventHeader, "EventHeader");
    OFF(EVENT_RECORD, BufferContext, "BufferContext");
    OFF(EVENT_RECORD, ExtendedDataCount, "ExtendedDataCount");
    OFF(EVENT_RECORD, UserDataLength, "UserDataLength");
    OFF(EVENT_RECORD, ExtendedData, "ExtendedData");
    OFF(EVENT_RECORD, UserData, "UserData");
    OFF(EVENT_RECORD, UserContext, "UserContext");
    pop_object();
}

static void event_trace_header(void) {
    push_object("EVENT_TRACE_HEADER");
    size_of("sizeof", sizeof(EVENT_TRACE_HEADER));
    OFF(EVENT_TRACE_HEADER, Size, "Size");
    OFF(EVENT_TRACE_HEADER, FieldTypeFlags, "FieldTypeFlags");
    OFF(EVENT_TRACE_HEADER, HeaderType, "HeaderType");
    OFF(EVENT_TRACE_HEADER, MarkerFlags, "MarkerFlags");
    OFF(EVENT_TRACE_HEADER, Version, "Version");
    OFF(EVENT_TRACE_HEADER, Class, "Class");
    OFF(EVENT_TRACE_HEADER, Class.Type, "Class_Type");
    OFF(EVENT_TRACE_HEADER, Class.Level, "Class_Level");
    OFF(EVENT_TRACE_HEADER, Class.Version, "Class_Version");
    OFF(EVENT_TRACE_HEADER, ThreadId, "ThreadId");
    OFF(EVENT_TRACE_HEADER, ProcessId, "ProcessId");
    OFF(EVENT_TRACE_HEADER, TimeStamp, "TimeStamp");
    OFF(EVENT_TRACE_HEADER, Guid, "Guid");
    OFF(EVENT_TRACE_HEADER, GuidPtr, "GuidPtr");
    OFF(EVENT_TRACE_HEADER, KernelTime, "KernelTime");
    OFF(EVENT_TRACE_HEADER, UserTime, "UserTime");
    OFF(EVENT_TRACE_HEADER, ProcessorTime, "ProcessorTime");
    OFF(EVENT_TRACE_HEADER, ClientContext, "ClientContext");
    OFF(EVENT_TRACE_HEADER, Flags, "Flags");
    pop_object();
}

static void event_trace(void) {
    push_object("EVENT_TRACE");
    size_of("sizeof", sizeof(EVENT_TRACE));
    OFF(EVENT_TRACE, Header, "Header");
    OFF(EVENT_TRACE, InstanceId, "InstanceId");
    OFF(EVENT_TRACE, ParentInstanceId, "ParentInstanceId");
    OFF(EVENT_TRACE, ParentGuid, "ParentGuid");
    OFF(EVENT_TRACE, MofData, "MofData");
    OFF(EVENT_TRACE, MofLength, "MofLength");
    OFF(EVENT_TRACE, ClientContext, "ClientContext");
    OFF(EVENT_TRACE, BufferContext, "BufferContext");
    pop_object();
}

static void trace_logfile_header(void) {
    push_object("TRACE_LOGFILE_HEADER");
    size_of("sizeof", sizeof(TRACE_LOGFILE_HEADER));
    OFF(TRACE_LOGFILE_HEADER, BufferSize, "BufferSize");
    OFF(TRACE_LOGFILE_HEADER, Version, "Version");
    OFF(TRACE_LOGFILE_HEADER, VersionDetail, "VersionDetail");
    OFF(TRACE_LOGFILE_HEADER, VersionDetail.MajorVersion, "VersionDetail_MajorVersion");
    OFF(TRACE_LOGFILE_HEADER, VersionDetail.MinorVersion, "VersionDetail_MinorVersion");
    OFF(TRACE_LOGFILE_HEADER, VersionDetail.SubVersion, "VersionDetail_SubVersion");
    OFF(TRACE_LOGFILE_HEADER, VersionDetail.SubMinorVersion, "VersionDetail_SubMinorVersion");
    OFF(TRACE_LOGFILE_HEADER, ProviderVersion, "ProviderVersion");
    OFF(TRACE_LOGFILE_HEADER, NumberOfProcessors, "NumberOfProcessors");
    OFF(TRACE_LOGFILE_HEADER, EndTime, "EndTime");
    OFF(TRACE_LOGFILE_HEADER, TimerResolution, "TimerResolution");
    OFF(TRACE_LOGFILE_HEADER, MaximumFileSize, "MaximumFileSize");
    OFF(TRACE_LOGFILE_HEADER, LogFileMode, "LogFileMode");
    OFF(TRACE_LOGFILE_HEADER, BuffersWritten, "BuffersWritten");
    OFF(TRACE_LOGFILE_HEADER, LogInstanceGuid, "LogInstanceGuid");
    OFF(TRACE_LOGFILE_HEADER, StartBuffers, "StartBuffers");
    OFF(TRACE_LOGFILE_HEADER, PointerSize, "PointerSize");
    OFF(TRACE_LOGFILE_HEADER, EventsLost, "EventsLost");
    OFF(TRACE_LOGFILE_HEADER, CpuSpeedInMHz, "CpuSpeedInMHz");
    OFF(TRACE_LOGFILE_HEADER, LoggerName, "LoggerName");
    OFF(TRACE_LOGFILE_HEADER, LogFileName, "LogFileName");
    OFF(TRACE_LOGFILE_HEADER, TimeZone, "TimeZone");
    OFF(TRACE_LOGFILE_HEADER, BootTime, "BootTime");
    OFF(TRACE_LOGFILE_HEADER, PerfFreq, "PerfFreq");
    OFF(TRACE_LOGFILE_HEADER, StartTime, "StartTime");
    OFF(TRACE_LOGFILE_HEADER, ReservedFlags, "ReservedFlags");
    OFF(TRACE_LOGFILE_HEADER, BuffersLost, "BuffersLost");
    pop_object();
}

static void event_header_extended_data_item(void) {
    size_t storage = 0;
    size_t bytes = 0;
    unsigned long long linkage_mask = 0;
    unsigned long long reserved_mask = 0;

    push_object("EVENT_HEADER_EXTENDED_DATA_ITEM");
    size_of("sizeof", sizeof(EVENT_HEADER_EXTENDED_DATA_ITEM));
    OFF(EVENT_HEADER_EXTENDED_DATA_ITEM, Reserved1, "Reserved1");
    OFF(EVENT_HEADER_EXTENDED_DATA_ITEM, ExtType, "ExtType");
    OFF(EVENT_HEADER_EXTENDED_DATA_ITEM, DataSize, "DataSize");
    OFF(EVENT_HEADER_EXTENDED_DATA_ITEM, DataPtr, "DataPtr");
    extended_bitfield(&storage, &bytes, &linkage_mask, &reserved_mask);
    num("Linkage_Reserved2_storage", (unsigned long long)storage);
    num("Linkage_Reserved2_bytes", (unsigned long long)bytes);
    num("Linkage_mask", linkage_mask);
    num("Reserved2_mask", reserved_mask);
    pop_object();
}

static void guid_layout(void) {
    push_object("GUID");
    size_of("sizeof", sizeof(GUID));
    OFF(GUID, Data1, "Data1");
    OFF(GUID, Data2, "Data2");
    OFF(GUID, Data3, "Data3");
    OFF(GUID, Data4, "Data4");
    pop_object();
}

static void systemtime_layout(void) {
    push_object("SYSTEMTIME");
    size_of("sizeof", sizeof(SYSTEMTIME));
    OFF(SYSTEMTIME, wYear, "wYear");
    OFF(SYSTEMTIME, wMonth, "wMonth");
    OFF(SYSTEMTIME, wDayOfWeek, "wDayOfWeek");
    OFF(SYSTEMTIME, wDay, "wDay");
    OFF(SYSTEMTIME, wHour, "wHour");
    OFF(SYSTEMTIME, wMinute, "wMinute");
    OFF(SYSTEMTIME, wSecond, "wSecond");
    OFF(SYSTEMTIME, wMilliseconds, "wMilliseconds");
    pop_object();
}

static void time_zone_information(void) {
    push_object("TIME_ZONE_INFORMATION");
    size_of("sizeof", sizeof(TIME_ZONE_INFORMATION));
    OFF(TIME_ZONE_INFORMATION, Bias, "Bias");
    OFF(TIME_ZONE_INFORMATION, StandardName, "StandardName");
    OFF(TIME_ZONE_INFORMATION, StandardDate, "StandardDate");
    OFF(TIME_ZONE_INFORMATION, StandardBias, "StandardBias");
    OFF(TIME_ZONE_INFORMATION, DaylightName, "DaylightName");
    OFF(TIME_ZONE_INFORMATION, DaylightDate, "DaylightDate");
    OFF(TIME_ZONE_INFORMATION, DaylightBias, "DaylightBias");
    pop_object();
}

static void etw_buffer_context(void) {
    push_object("ETW_BUFFER_CONTEXT");
    size_of("sizeof", sizeof(ETW_BUFFER_CONTEXT));
    OFF(ETW_BUFFER_CONTEXT, ProcessorNumber, "ProcessorNumber");
    OFF(ETW_BUFFER_CONTEXT, Alignment, "Alignment");
    OFF(ETW_BUFFER_CONTEXT, ProcessorIndex, "ProcessorIndex");
    OFF(ETW_BUFFER_CONTEXT, LoggerId, "LoggerId");
    pop_object();
}

static void event_trace_logfilew(void) {
    push_object("EVENT_TRACE_LOGFILEW");
    size_of("sizeof", sizeof(EVENT_TRACE_LOGFILEW));
    OFF(EVENT_TRACE_LOGFILEW, LogFileName, "LogFileName");
    OFF(EVENT_TRACE_LOGFILEW, LoggerName, "LoggerName");
    OFF(EVENT_TRACE_LOGFILEW, CurrentTime, "CurrentTime");
    OFF(EVENT_TRACE_LOGFILEW, BuffersRead, "BuffersRead");
    OFF(EVENT_TRACE_LOGFILEW, LogFileMode, "LogFileMode");
    OFF(EVENT_TRACE_LOGFILEW, ProcessTraceMode, "ProcessTraceMode");
    OFF(EVENT_TRACE_LOGFILEW, CurrentEvent, "CurrentEvent");
    OFF(EVENT_TRACE_LOGFILEW, LogfileHeader, "LogfileHeader");
    OFF(EVENT_TRACE_LOGFILEW, BufferCallback, "BufferCallback");
    OFF(EVENT_TRACE_LOGFILEW, BufferSize, "BufferSize");
    OFF(EVENT_TRACE_LOGFILEW, Filled, "Filled");
    OFF(EVENT_TRACE_LOGFILEW, EventsLost, "EventsLost");
    OFF(EVENT_TRACE_LOGFILEW, EventCallback, "EventCallback");
    OFF(EVENT_TRACE_LOGFILEW, EventRecordCallback, "EventRecordCallback");
    OFF(EVENT_TRACE_LOGFILEW, IsKernelTrace, "IsKernelTrace");
    OFF(EVENT_TRACE_LOGFILEW, Context, "Context");
    pop_object();
}

int main(void) {
    push_object(NULL);
    num("schema", 1);
    num("arch", ABI_ARCH);
    primitives();
    wnode_header();
    event_trace_properties();
    event_descriptor();
    event_header();
    event_record();
    event_trace_header();
    event_trace();
    trace_logfile_header();
    event_trace_logfilew();
    event_header_extended_data_item();
    guid_layout();
    systemtime_layout();
    time_zone_information();
    etw_buffer_context();
    pop_object();
    appendf("\n");
    if (fwrite(g_out, 1, g_len, stdout) != g_len) {
        return 3;
    }
    return 0;
}
