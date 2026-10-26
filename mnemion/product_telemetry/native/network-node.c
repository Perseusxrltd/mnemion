/* SPDX-License-Identifier: MIT
 * The stable Node-API C interface, resolved from the current Node/Electron
 * process. No Node/V8 headers, downloads, imported node.exe or ABI rebuilds.
 * This same binary exposes network-state.h to the packaged Python runtime. */
#if defined(__linux__) && !defined(_GNU_SOURCE)
/* Older glibc headers hide RTLD_DEFAULT under strict C11 without this feature
 * selection. Set it before network-state.h pulls in any system header. */
#define _GNU_SOURCE
#endif
#include "network-state.h"
#include <stdlib.h>
#include <string.h>
#if defined(_WIN32)
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#else
#include <dlfcn.h>
#endif

typedef struct napi_env__ *NEnv;
typedef struct napi_value__ *NValue;
typedef struct napi_callback_info__ *NInfo;
typedef struct napi_deferred__ *NDeferred;
typedef struct napi_async_work__ *NWork;
typedef NValue (*NCallback)(NEnv, NInfo);
typedef void (*NExecute)(NEnv, void *);
typedef void (*NComplete)(NEnv, int, void *);
static struct {
    int (*uint32)(NEnv, uint32_t, NValue *);
    int (*number)(NEnv, double, NValue *);
    int (*array)(NEnv, size_t, NValue *);
    int (*element)(NEnv, NValue, uint32_t, NValue);
    int (*string)(NEnv, const char *, size_t, NValue *);
    int (*function)(NEnv, const char *, size_t, NCallback, void *, NValue *);
    int (*property)(NEnv, NValue, const char *, NValue);
    int (*promise)(NEnv, NDeferred *, NValue *);
    int (*resolve)(NEnv, NDeferred, NValue);
    int (*create_work)(NEnv, NValue, NValue, NExecute, NComplete, void *, NWork *);
    int (*queue_work)(NEnv, NWork);
    int (*delete_work)(NEnv, NWork);
} api;

static int host_symbol(void *target, size_t size, const char *name) {
#if defined(_WIN32)
    FARPROC symbol = GetProcAddress(GetModuleHandleW(NULL), name);
#else
    void *symbol = dlsym(RTLD_DEFAULT, name);
#endif
    if (!symbol || size != sizeof(symbol)) return 0;
    memcpy(target, &symbol, size);
    return 1;
}

typedef struct { NWork work; NDeferred deferred; uint32_t state; } Observation;

static void measure(NEnv env, void *data) {
    (void)env;
    ((Observation *)data)->state = mnemion_network_state_v1();
}

static void complete(NEnv env, int status, void *data) {
    Observation *observation = data;
    NValue value = NULL;
    if (api.uint32(env, status == 0 ? observation->state : MNM_UNKNOWN, &value) == 0)
        (void)api.resolve(env, observation->deferred, value);
    (void)api.delete_work(env, observation->work);
    free(observation);
}

static NValue read_state(NEnv env, NInfo info) {
    (void)info;
    Observation *observation = calloc(1, sizeof(*observation));
    NValue promise = NULL, name = NULL;
    if (!observation) return NULL;
    if (api.promise(env, &observation->deferred, &promise) != 0) { free(observation); return NULL; }
    if (api.string(env, "mnemion.network-cost", 20, &name) != 0 ||
        api.create_work(env, NULL, name, measure, complete, observation, &observation->work) != 0 ||
        api.queue_work(env, observation->work) != 0) {
        NValue unknown = NULL;
        if (api.uint32(env, MNM_UNKNOWN, &unknown) == 0) (void)api.resolve(env, observation->deferred, unknown);
        if (observation->work) (void)api.delete_work(env, observation->work);
        free(observation);
    }
    return promise;
}

static NValue read_cpu_totals(NEnv env, NInfo info) {
    (void)info;
    MnmCpuTotals totals = {0};
    const int available = mnemion_cpu_totals_v1(&totals);
    NValue result = NULL, value = NULL;
    if (api.array(env, available ? 3 : 0, &result) != 0) return NULL;
    if (!available) return result;
    const double values[] = {(double)totals.idle, (double)totals.total, (double)totals.count};
    for (uint32_t i = 0; i < 3; ++i) {
        if (api.number(env, values[i], &value) != 0 || api.element(env, result, i, value) != 0) return NULL;
    }
    return result;
}

static NValue review_clock(NEnv env, int initialize) {
    MnmReviewClock clock = {0};
    const int available = mnemion_review_clock_v1(initialize, &clock);
    NValue result = NULL, elapsed = NULL, epoch = NULL;
    if (api.array(env, available ? 2 : 0, &result) != 0) return NULL;
    if (!available) return result;
    static const char hex[] = "0123456789abcdef";
    char encoded[33] = {0};
    for (size_t at = 0; at < sizeof(clock.epoch); ++at) {
        encoded[at * 2] = hex[clock.epoch[at] >> 4];
        encoded[at * 2 + 1] = hex[clock.epoch[at] & 15];
    }
    if (api.number(env, (double)clock.elapsed_ms, &elapsed) != 0 ||
        api.string(env, encoded, 32, &epoch) != 0 ||
        api.element(env, result, 0, elapsed) != 0 || api.element(env, result, 1, epoch) != 0) return NULL;
    return result;
}

static NValue read_review_clock(NEnv env, NInfo info) {
    (void)info;
    return review_clock(env, 0);
}

static NValue initialize_review_clock(NEnv env, NInfo info) {
    (void)info;
    return review_clock(env, 1);
}

MNM_EXPORT int32_t node_api_module_get_api_version_v1(void) { return 8; }
MNM_EXPORT NValue napi_register_module_v1(NEnv env, NValue exports) {
#define LOAD(field, name) if (!host_symbol(&api.field, sizeof(api.field), name)) return NULL
    LOAD(uint32, "napi_create_uint32");
    LOAD(number, "napi_create_double");
    LOAD(array, "napi_create_array_with_length");
    LOAD(element, "napi_set_element");
    LOAD(string, "napi_create_string_utf8");
    LOAD(function, "napi_create_function");
    LOAD(property, "napi_set_named_property");
    LOAD(promise, "napi_create_promise");
    LOAD(resolve, "napi_resolve_deferred");
    LOAD(create_work, "napi_create_async_work");
    LOAD(queue_work, "napi_queue_async_work");
    LOAD(delete_work, "napi_delete_async_work");
#undef LOAD
    NValue function = NULL;
    if (api.function(env, "readState", 9, read_state, NULL, &function) != 0 ||
        api.property(env, exports, "readState", function) != 0) return NULL;
    if (api.function(env, "readCpuTotals", 13, read_cpu_totals, NULL, &function) != 0 ||
        api.property(env, exports, "readCpuTotals", function) != 0) return NULL;
    if (api.function(env, "readReviewClock", 15, read_review_clock, NULL, &function) != 0 ||
        api.property(env, exports, "readReviewClock", function) != 0) return NULL;
    if (api.function(env, "initializeReviewClock", 21, initialize_review_clock, NULL, &function) != 0 ||
        api.property(env, exports, "initializeReviewClock", function) != 0) return NULL;
    return exports;
}
