"""Keep native dependency checks strict without confusing a dylib's own name."""

import pytest

from deploy.build_intel_crypto import system_dependencies


IDENTITY = "@rpath/cryptography.hazmat.bindings._rust.abi3.so"
SYSTEM = "/usr/lib/libSystem.B.dylib"


def listing(*libraries):
    return "native.so:\n" + "".join(
        f"\t{name} (compatibility version 1.0.0, current version 1.0.0)\n" for name in libraries
    )


def test_own_install_name_is_not_an_external_runtime_dependency():
    # otool -L prints LC_ID_DYLIB before LC_LOAD_DYLIB entries; -D identifies it.
    assert system_dependencies(
        listing(IDENTITY, "/usr/lib/libiconv.2.dylib", SYSTEM), f"native.so:\n{IDENTITY}\n"
    ) == ["/usr/lib/libiconv.2.dylib", SYSTEM]
    # Mach-O bundles may have no install name.
    assert system_dependencies(listing(SYSTEM), "native.so:\n") == [SYSTEM]


@pytest.mark.parametrize(
    "library",
    [
        "@rpath/libssl.3.dylib",
        "/usr/local/opt/openssl/lib/libcrypto.3.dylib",
        "/opt/homebrew/lib/libcrypto.3.dylib",
        "/usr/lib/../local/lib/libcrypto.3.dylib",
        IDENTITY,
    ],
)
def test_non_system_dependency_cannot_hide_behind_the_install_name(library):
    with pytest.raises(ValueError, match="non-system"):
        system_dependencies(listing(IDENTITY, SYSTEM, library), f"native.so:\n{IDENTITY}\n")


@pytest.mark.parametrize(
    "dependencies,identities",
    [
        (listing(SYSTEM), f"native.so:\n{IDENTITY}\n"),
        (listing(IDENTITY), f"native.so:\n{IDENTITY}\n"),
        (listing(IDENTITY, SYSTEM), f"native.so:\n{IDENTITY}\nextra\n"),
        ("native.so:\n\tunknown output\n", "native.so:\n"),
        ("", ""),
    ],
)
def test_incomplete_or_inconsistent_inspection_fails_closed(dependencies, identities):
    with pytest.raises(ValueError):
        system_dependencies(dependencies, identities)
