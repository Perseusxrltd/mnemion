/* SPDX-License-Identifier: MIT
 * The stable Node-API C interface, resolved from the current Node/Electron
 * process. No Node/V8 headers, downloads, imported node.exe or ABI rebuilds.
 * This same binary exposes network-state.h to the packaged Python runtime. */
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

MNM_EXPORT int32_t node_api_module_get_api_version_v1(void) { return 8; }
MNM_EXPORT NValue napi_register_module_v1(NEnv env, NValue exports) {
#define LOAD(field, name) if (!host_symbol(&api.field, sizeof(api.field), name)) return NULL
    LOAD(uint32, "napi_create_uint32");
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
    return exports;
}
