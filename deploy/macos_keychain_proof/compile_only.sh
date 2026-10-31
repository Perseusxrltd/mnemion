#!/bin/bash
# Compile-only lane for the disposable Keychain helper proof.
# It does not execute the binaries it links, and it does not call codesign,
# security, or anything that reads or writes a Keychain. It is not native acceptance.

set -eu

if [ "$#" -ne 3 ]; then
  echo "usage: compile_only.sh --compile-only arm64|x86_64 output-dir" >&2
  exit 2
fi
if [ "$1" != "--compile-only" ]; then
  echo "refusing a lane that is not compile_only" >&2
  exit 2
fi

arch="$2"
out="$3"
if [ "$arch" != "arm64" ] && [ "$arch" != "x86_64" ]; then
  echo "arch must be arm64 or x86_64" >&2
  exit 2
fi

root="deploy/macos_keychain_proof"
pin="$root/generated/parent_pin.h"
mkdir -p "$out"
receipt="$out/receipt.txt"
echo "lane=compile_only" > "$receipt"
echo "runtime_validation=not_performed" >> "$receipt"
echo "native_acceptance=not_claimed" >> "$receipt"
echo "binary_executed=no" >> "$receipt"
echo "codesign=not_called" >> "$receipt"
echo "security_tool=not_called" >> "$receipt"
echo "certificate_der_comparison=not_performed" >> "$receipt"
echo "keychain=not_modified" >> "$receipt"
echo "electron=not_used" >> "$receipt"
echo "arch=$arch" >> "$receipt"
echo "deployment_target=13.0" >> "$receipt"

if [ ! -f "$pin" ]; then
  echo "missing compile_only pin header" | tee -a "$receipt" >&2
  exit 2
fi
if ! grep -F -q 'MNEMION_PIN_CLASS "compile_only"' "$pin"; then
  echo "pin header is not compile_only" | tee -a "$receipt" >&2
  exit 2
fi
if ! grep -F -q 'compile_only: not a certificate' "$pin"; then
  echo "pin header is missing compile_only metadata" | tee -a "$receipt" >&2
  exit 2
fi
if grep -F -q 'BEGIN PRIVATE' "$pin"; then
  echo "pin header contains a private key" | tee -a "$receipt" >&2
  exit 2
fi

needed="$root/HelperInfo.plist"
if [ ! -f "$needed" ]; then
  echo "missing $needed" | tee -a "$receipt" >&2
  exit 2
fi
needed="$root/ParentInfo.plist"
if [ ! -f "$needed" ]; then
  echo "missing $needed" | tee -a "$receipt" >&2
  exit 2
fi
needed="$root/helper_main.m"
if [ ! -f "$needed" ]; then
  echo "missing $needed" | tee -a "$receipt" >&2
  exit 2
fi
needed="$root/auth.m"
if [ ! -f "$needed" ]; then
  echo "missing $needed" | tee -a "$receipt" >&2
  exit 2
fi
needed="$root/key_item.m"
if [ ! -f "$needed" ]; then
  echo "missing $needed" | tee -a "$receipt" >&2
  exit 2
fi
needed="$root/v10_crypt.c"
if [ ! -f "$needed" ]; then
  echo "missing $needed" | tee -a "$receipt" >&2
  exit 2
fi
needed="$root/parent_main.m"
if [ ! -f "$needed" ]; then
  echo "missing $needed" | tee -a "$receipt" >&2
  exit 2
fi
needed="$root/bundle_manifest.c"
if [ ! -f "$needed" ]; then
  echo "missing $needed" | tee -a "$receipt" >&2
  exit 2
fi
needed="$root/signing.m"
if [ ! -f "$needed" ]; then
  echo "missing $needed" | tee -a "$receipt" >&2
  exit 2
fi
needed="$root/identity_dump.m"
if [ ! -f "$needed" ]; then
  echo "missing $needed" | tee -a "$receipt" >&2
  exit 2
fi

cp "$root/HelperInfo.plist" "$out/HelperInfo.plist"
cp "$root/ParentInfo.plist" "$out/ParentInfo.plist"
mkdir -p "$out/bin"

failed=0

run_clang() {
  name="$1"
  shift
  log="$out/$name.txt"
  set +e
  clang "$@" >"$log" 2>&1
  status=$?
  set -e
  echo "compiler_exit=$status" >>"$log"
  if [ "$status" -ne 0 ]; then
    failed=1
  fi
}

run_clang helper \
  -arch "$arch" \
  -mmacosx-version-min=13.0 \
  -std=gnu11 \
  -fno-objc-arc \
  -fblocks \
  -DOS_OBJECT_USE_OBJC=0 \
  -Werror \
  -Wall \
  -Wextra \
  -Werror=implicit-function-declaration \
  -I "$root" \
  -I "$root/generated" \
  -o "$out/bin/MnemionCredentialHelper" \
  "$root/helper_main.m" \
  "$root/auth.m" \
  "$root/key_item.m" \
  "$root/v10_crypt.c" \
  -framework Security \
  -framework CoreFoundation

run_clang parent \
  -arch "$arch" \
  -mmacosx-version-min=13.0 \
  -std=gnu11 \
  -fno-objc-arc \
  -fblocks \
  -DOS_OBJECT_USE_OBJC=0 \
  -Werror \
  -Wall \
  -Wextra \
  -Werror=implicit-function-declaration \
  -I "$root" \
  -I "$root/generated" \
  -o "$out/bin/MnemionCredentialParent" \
  "$root/parent_main.m" \
  "$root/auth.m" \
  "$root/bundle_manifest.c" \
  "$root/signing.m" \
  -framework Security \
  -framework CoreFoundation

run_clang identity \
  -arch "$arch" \
  -mmacosx-version-min=13.0 \
  -std=gnu11 \
  -fno-objc-arc \
  -fblocks \
  -DOS_OBJECT_USE_OBJC=0 \
  -Werror \
  -Wall \
  -Wextra \
  -Werror=implicit-function-declaration \
  -I "$root" \
  -o "$out/bin/MnemionIdentityDump" \
  "$root/identity_dump.m" \
  "$root/signing.m" \
  -framework Security \
  -framework CoreFoundation

set +e
wc -c "$out/bin/MnemionCredentialHelper" >> "$out/sizes.txt"
wc -c "$out/bin/MnemionCredentialParent" >> "$out/sizes.txt"
wc -c "$out/bin/MnemionIdentityDump" >> "$out/sizes.txt"
set -e
rm -f "$out/bin/MnemionCredentialHelper" "$out/bin/MnemionCredentialParent" "$out/bin/MnemionIdentityDump"
rmdir "$out/bin" || true

if [ "$failed" -ne 0 ]; then
  echo "compile_result=failed" >> "$receipt"
  exit 1
fi
echo "compile_result=objects_linked_not_executed" >> "$receipt"
exit 0
