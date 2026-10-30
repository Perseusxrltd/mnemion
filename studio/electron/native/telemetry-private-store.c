/* Process entry for the shared read-only check. Admission does not spawn this. */
#include "../../../mnemion/product_telemetry/native/private-store.h"

int wmain(int argc, wchar_t **argv) {
    if (argc != 3) return 1;
    return mnemion_private_store_accessible(argv[1], argv[2]) ? 0 : 1;
}
