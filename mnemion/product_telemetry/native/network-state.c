/* SPDX-License-Identifier: MIT
 * Read OS cost policy only. Never enumerate names/addresses, make an Internet
 * request, change a network setting, log, or retain an OS connection. */
#include "network-state.h"
#include <stddef.h>
#include <string.h>

uint32_t mnm_windows_cost(uint32_t cost, uint32_t level, int approaching, int over, int roaming) {
    uint32_t value = MNM_OBSERVED;
    if (cost == 2u || cost == 3u || approaching || over || roaming) value |= MNM_METERED;
    else if (cost == 1u) value |= MNM_UNMETERED;
    if (cost > 3u || level != 3u) value |= MNM_CONSTRAINED;
    return value;
}

uint32_t mnm_linux_cost(uint32_t cost, uint32_t state) {
    uint32_t value = MNM_OBSERVED;
    /* NetworkManager's explicit NO is different from its guessed NO. */
    if (cost == 1u || cost == 3u) value |= MNM_METERED;
    else if (cost == 2u) value |= MNM_UNMETERED;
    else if (cost != 0u && cost != 4u) value |= MNM_CONSTRAINED;
    if (state != 70u) value |= MNM_CONSTRAINED;
    return value;
}

#if defined(_WIN32)
#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <windows.h>
#include <iphlpapi.h>

typedef DWORD (WINAPI *MnmConnectivityHint)(NL_NETWORK_CONNECTIVITY_HINT *);
static INIT_ONCE hint_once = INIT_ONCE_STATIC_INIT;
static MnmConnectivityHint connectivity_hint;

static BOOL CALLBACK load_hint(PINIT_ONCE once, PVOID parameter, PVOID *context) {
    (void)once; (void)parameter; (void)context;
    /* Windows 10 2004 added this API. Older builds stay unknown and load
     * normally; never initialize the much heavier COM network manager. */
    HMODULE library = LoadLibraryExW(L"iphlpapi.dll", NULL, LOAD_LIBRARY_SEARCH_SYSTEM32);
    if (library) {
        FARPROC symbol = GetProcAddress(library, "GetNetworkConnectivityHint");
        if (symbol && sizeof(symbol) == sizeof(connectivity_hint))
            memcpy(&connectivity_hint, &symbol, sizeof(symbol));
        else FreeLibrary(library);
    }
    return TRUE;
}

MNM_EXPORT uint32_t mnemion_network_state_v1(void) {
    (void)InitOnceExecuteOnce(&hint_once, load_hint, NULL, NULL);
    if (!connectivity_hint) return MNM_UNKNOWN;
    NL_NETWORK_CONNECTIVITY_HINT hint = {0};
    DWORD result = connectivity_hint(&hint);
    if (result == ERROR_NO_NETWORK) return MNM_OBSERVED | MNM_CONSTRAINED;
    if (result != NO_ERROR) return MNM_UNKNOWN;
    return mnm_windows_cost((uint32_t)hint.ConnectivityCost, (uint32_t)hint.ConnectivityLevel,
                            hint.ApproachingDataLimit, hint.OverDataLimit, hint.Roaming);
}

#elif defined(__APPLE__)
#include <Network/Network.h>
#include <dispatch/dispatch.h>
#include <stdatomic.h>

MNM_EXPORT uint32_t mnemion_network_state_v1(void) {
    /* Objective-C ARC retains captured dispatch objects until the cancelled
     * monitor releases its callback, even when the bounded first read times out. */
    __block _Atomic(uint32_t) value = MNM_UNKNOWN;
    dispatch_semaphore_t ready = dispatch_semaphore_create(0);
    dispatch_queue_t queue = dispatch_queue_create("com.perseusxr.mnemion.network-cost", DISPATCH_QUEUE_SERIAL);
    nw_path_monitor_t monitor = nw_path_monitor_create();
    if (!ready || !queue || !monitor) return MNM_UNKNOWN;
    nw_path_monitor_set_update_handler(monitor, ^(nw_path_t path) {
        uint32_t observed = MNM_OBSERVED;
        if (nw_path_get_status(path) != nw_path_status_satisfied || nw_path_is_constrained(path))
            observed |= MNM_CONSTRAINED;
        observed |= nw_path_is_expensive(path) ? MNM_METERED : MNM_UNMETERED;
        atomic_store(&value, observed);
        dispatch_semaphore_signal(ready);
    });
    nw_path_monitor_set_queue(monitor, queue);
    nw_path_monitor_start(monitor);
    (void)dispatch_semaphore_wait(ready, dispatch_time(DISPATCH_TIME_NOW, 200 * NSEC_PER_MSEC));
    nw_path_monitor_cancel(monitor);
    return atomic_load(&value);
}

#elif defined(__linux__)
#include <dlfcn.h>
#include <pthread.h>
#include <time.h>

/* D-Bus's published stable C ABI. Opaque iterator storage is deliberately
 * larger than DBusMessageIter (72 bytes on supported 64-bit targets), aligned
 * for its pointer fields. No message or string is decoded except two uint32s. */
typedef union { void *alignment; unsigned char storage[128]; } MnmDbusIter;
typedef struct {
    void *library;
    int ready;
    int (*threads_init)(void);
    void *(*open_private)(const char *, void *);
    void (*exit_on_disconnect)(void *, int);
    void (*max_message_size)(void *, long);
    void (*max_received_size)(void *, long);
    void (*max_message_fds)(void *, long);
    void (*max_received_fds)(void *, long);
    void *(*new_call)(const char *, const char *, const char *, const char *);
    void (*auto_start)(void *, int);
    int (*append_args)(void *, int, ...);
    int (*send_pending)(void *, void *, void **, int);
    int (*read_dispatch)(void *, int);
    int (*completed)(void *);
    void *(*steal_reply)(void *);
    void (*cancel_pending)(void *);
    void (*unref_pending)(void *);
    int (*message_type)(void *);
    int (*iter_init)(void *, void *);
    int (*iter_type)(void *);
    void (*iter_recurse)(void *, void *);
    void (*iter_basic)(void *, void *);
    int (*iter_next)(void *);
    void (*message_unref)(void *);
    void (*close)(void *);
    void (*unref)(void *);
} MnmDbus;
static MnmDbus bus_api;
static pthread_once_t bus_once = PTHREAD_ONCE_INIT;

static int bus_symbol(void *target, size_t size, const char *name) {
    void *value = dlsym(bus_api.library, name);
    if (!value || size != sizeof(value)) return 0;
    memcpy(target, &value, size);
    return 1;
}

static void bus_load(void) {
    bus_api.library = dlopen("libdbus-1.so.3", RTLD_NOW | RTLD_LOCAL);
    if (!bus_api.library) return;
#define LOAD(field, name) if (!bus_symbol(&bus_api.field, sizeof(bus_api.field), name)) return
    LOAD(threads_init, "dbus_threads_init_default");
    LOAD(open_private, "dbus_connection_open_private");
    LOAD(exit_on_disconnect, "dbus_connection_set_exit_on_disconnect");
    LOAD(max_message_size, "dbus_connection_set_max_message_size");
    LOAD(max_received_size, "dbus_connection_set_max_received_size");
    LOAD(max_message_fds, "dbus_connection_set_max_message_unix_fds");
    LOAD(max_received_fds, "dbus_connection_set_max_received_unix_fds");
    LOAD(new_call, "dbus_message_new_method_call");
    LOAD(auto_start, "dbus_message_set_auto_start");
    LOAD(append_args, "dbus_message_append_args");
    LOAD(send_pending, "dbus_connection_send_with_reply");
    LOAD(read_dispatch, "dbus_connection_read_write_dispatch");
    LOAD(completed, "dbus_pending_call_get_completed");
    LOAD(steal_reply, "dbus_pending_call_steal_reply");
    LOAD(cancel_pending, "dbus_pending_call_cancel");
    LOAD(unref_pending, "dbus_pending_call_unref");
    LOAD(message_type, "dbus_message_get_type");
    LOAD(iter_init, "dbus_message_iter_init");
    LOAD(iter_type, "dbus_message_iter_get_arg_type");
    LOAD(iter_recurse, "dbus_message_iter_recurse");
    LOAD(iter_basic, "dbus_message_iter_get_basic");
    LOAD(iter_next, "dbus_message_iter_next");
    LOAD(message_unref, "dbus_message_unref");
    LOAD(close, "dbus_connection_close");
    LOAD(unref, "dbus_connection_unref");
#undef LOAD
    bus_api.ready = bus_api.threads_init();
}

static uint64_t bus_clock(void) {
    struct timespec now;
    if (clock_gettime(CLOCK_MONOTONIC, &now) != 0 || now.tv_sec < 0) return 0;
    return (uint64_t)now.tv_sec * 1000u + (uint64_t)now.tv_nsec / 1000000u;
}

static void *bus_exchange(void *connection, void *call) {
    void *pending = NULL, *reply = NULL;
    const uint64_t started = bus_clock();
    if (!started || !bus_api.send_pending(connection, call, &pending, 200) || !pending) return NULL;
    /* The blocking pending-call API can exceed its timeout during auth.
     * Nonblocking sends plus bounded dispatch also consume bus control signals
     * instead of filling the small receive quota while waiting for a reply. */
    while (!bus_api.completed(pending)) {
        const uint64_t now = bus_clock();
        if (now < started || now - started >= 200u) break;
        const uint64_t remaining = 200u - (now - started);
        if (!bus_api.read_dispatch(connection, remaining > 10u ? 10 : (int)remaining)) break;
    }
    if (bus_api.completed(pending)) reply = bus_api.steal_reply(pending);
    bus_api.cancel_pending(pending);
    bus_api.unref_pending(pending);
    if (reply && bus_api.message_type(reply) != 2) {
        bus_api.message_unref(reply);
        reply = NULL;
    }
    return reply;
}

static int bus_uint(void *connection, const char *property, uint32_t *value) {
    const char *interface = "org.freedesktop.NetworkManager";
    void *call = bus_api.new_call(interface, "/org/freedesktop/NetworkManager",
                                 "org.freedesktop.DBus.Properties", "Get");
    if (!call) return 0;
    bus_api.auto_start(call, 0);
    void *reply = NULL;
    if (bus_api.append_args(call, 's', &interface, 's', &property, 0))
        reply = bus_exchange(connection, call);
    bus_api.message_unref(call);
    if (!reply) return 0;
    MnmDbusIter top = {0}, variant = {0};
    int accepted = 0;
    if (bus_api.iter_init(reply, &top) && bus_api.iter_type(&top) == 'v') {
        bus_api.iter_recurse(&top, &variant);
        if (bus_api.iter_type(&variant) == 'u') {
            bus_api.iter_basic(&variant, value);
            accepted = !bus_api.iter_next(&variant) && !bus_api.iter_next(&top);
        }
    }
    bus_api.message_unref(reply);
    return accepted;
}

MNM_EXPORT uint32_t mnemion_network_state_v1(void) {
    (void)pthread_once(&bus_once, bus_load);
    if (!bus_api.ready) return MNM_UNKNOWN;
    /* Ignore DBUS_* environment overrides, including possible remote addresses.
     * The private test build alone may select its isolated Unix bus socket. */
#ifndef MNEMION_NETWORK_TEST_BUS
#define MNEMION_NETWORK_TEST_BUS "unix:path=/run/dbus/system_bus_socket"
#endif
    void *connection = bus_api.open_private(MNEMION_NETWORK_TEST_BUS, NULL);
    if (!connection) return MNM_UNKNOWN;
    bus_api.exit_on_disconnect(connection, 0);
    bus_api.max_message_size(connection, 4096);
    bus_api.max_received_size(connection, 8192);
    bus_api.max_message_fds(connection, 0);
    /* The aggregate quota must stay positive or libdbus disables all reads.
     * Zero per-message descriptors rejects any FD-bearing reply. */
    bus_api.max_received_fds(connection, 1);
    uint32_t cost = 0, state = 0, result = MNM_UNKNOWN;
    /* Register with a bounded Hello rather than dbus_bus_register's default
     * wait. The unique bus name in its response is discarded without reading. */
    void *hello = bus_api.new_call("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "Hello");
    if (hello) {
        bus_api.auto_start(hello, 0);
        void *reply = bus_exchange(connection, hello);
        bus_api.message_unref(hello);
        if (reply) {
            bus_api.message_unref(reply);
            if (bus_uint(connection, "Metered", &cost) && bus_uint(connection, "State", &state))
                result = mnm_linux_cost(cost, state);
        }
    }
    bus_api.close(connection); bus_api.unref(connection);
    return result;
}
#else
MNM_EXPORT uint32_t mnemion_network_state_v1(void) { return MNM_UNKNOWN; }
#endif
