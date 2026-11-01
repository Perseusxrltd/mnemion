#!/bin/bash
# Compile-only lane for the disposable Keychain helper proof.
# It does not execute the binaries it links, and it does not call codesign,
# security, or anything that reads or writes a Keychain. It is not native acceptance.
# The three linked binaries live under "$out/bin". EXIT removes those three
# paths, including after a compiler error. INT and TERM remove the same three
# paths and exit 1, so a cancel does not resume the script. Logs stay.

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
caller_pin="$root/generated/caller_pin.h"
parent_pin="$root/generated/parent_pin.h"
store_config="$root/generated/fixture_store_config.h"
mkdir -p "$out"
receipt="$out/receipt.txt"
echo "lane=compile_only" > "$receipt"
echo "runtime_validation=not_performed" >> "$receipt"
echo "native_acceptance=not_claimed" >> "$receipt"
echo "binary_executed=no" >> "$receipt"
echo "codesign=not_called" >> "$receipt"
echo "security_tool=not_called" >> "$receipt"
echo "certificate_der_comparison=not_performed" >> "$receipt"
echo "fixture_store_guard=source_linked_not_executed" >> "$receipt"
echo "interaction_bracket=source_linked_not_executed" >> "$receipt"
echo "sealed_fixture=source_linked_not_executed" >> "$receipt"
echo "creation_marker=source_linked_not_executed" >> "$receipt"
echo "exact_helper_pins=parent_only" >> "$receipt"
echo "signer_controller=not_this_lane" >> "$receipt"
echo "keychain=not_modified" >> "$receipt"
echo "electron=not_used" >> "$receipt"
echo "arch=$arch" >> "$receipt"
echo "deployment_target=13.0" >> "$receipt"

if [ ! -f "$caller_pin" ] || [ ! -f "$parent_pin" ] || [ ! -f "$store_config" ]; then
  echo "missing compile_only pin or store header" | tee -a "$receipt" >&2
  exit 2
fi
if ! grep -F -q 'MNEMION_PIN_CLASS "compile_only"' "$caller_pin"; then
  echo "caller pin header is not compile_only" | tee -a "$receipt" >&2
  exit 2
fi
if ! grep -F -q 'compile_only: not a certificate' "$caller_pin"; then
  echo "caller pin header is missing compile_only metadata" | tee -a "$receipt" >&2
  exit 2
fi
if grep -F -q 'MNEMION_HELPER_CDHASH' "$caller_pin"; then
  echo "caller pin header contains parent-only helper pins" | tee -a "$receipt" >&2
  exit 2
fi
if ! grep -F -q 'MNEMION_HELPER_CDHASH' "$parent_pin"; then
  echo "parent pin header is missing the helper cdhash" | tee -a "$receipt" >&2
  exit 2
fi
if grep -F -q 'MNEMION_PIN_CLASS' "$parent_pin"; then
  echo "parent pin header must not carry the caller pin class" | tee -a "$receipt" >&2
  exit 2
fi
if ! grep -F -q 'MNEMION_FIXTURE_STORE_CLASS "compile_only"' "$store_config"; then
  echo "fixture store config is not compile_only" | tee -a "$receipt" >&2
  exit 2
fi
if ! grep -F -q 'compile_only: not an owned store' "$store_config"; then
  echo "fixture store config is missing compile_only metadata" | tee -a "$receipt" >&2
  exit 2
fi
for macro in \
  MNEMION_FIXTURE_RUN_DIRECTORY \
  MNEMION_FIXTURE_NONCE \
  MNEMION_FIXTURE_EUID \
  MNEMION_FIXTURE_RUN_DEVICE \
  MNEMION_FIXTURE_RUN_INODE \
  MNEMION_FIXTURE_STORE_DEVICE \
  MNEMION_FIXTURE_STORE_INODE \
  MNEMION_FIXTURE_SERVICE \
  MNEMION_FIXTURE_ACCOUNT
do
  if ! grep -F -q "#define ${macro} " "$store_config"; then
    echo "fixture store config is missing $macro" | tee -a "$receipt" >&2
    exit 2
  fi
done
if grep -F -q 'BEGIN PRIVATE' "$caller_pin" "$parent_pin" "$store_config"; then
  echo "generated header contains a private key" | tee -a "$receipt" >&2
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
needed="$root/fixture_store.m"
if [ ! -f "$needed" ]; then
  echo "missing $needed" | tee -a "$receipt" >&2
  exit 2
fi
needed="$root/fixture_store_syntax.c"
if [ ! -f "$needed" ]; then
  echo "missing $needed" | tee -a "$receipt" >&2
  exit 2
fi
needed="$root/exact_helper.m"
if [ ! -f "$needed" ]; then
  echo "missing $needed" | tee -a "$receipt" >&2
  exit 2
fi

cp "$root/HelperInfo.plist" "$out/HelperInfo.plist"
cp "$root/ParentInfo.plist" "$out/ParentInfo.plist"
mkdir -p "$out/bin"
helper_bin="$out/bin/MnemionCredentialHelper"
parent_bin="$out/bin/MnemionCredentialParent"
identity_bin="$out/bin/MnemionIdentityDump"
remove_linked_bins() {
  rm -f "$helper_bin" "$parent_bin" "$identity_bin" || true
  rmdir "$out/bin" 2>/dev/null || true
}
stop_after_signal() {
  echo "compile_result=interrupted" >> "$receipt" || true
  remove_linked_bins
  trap - EXIT INT TERM
  exit 1
}
trap remove_linked_bins EXIT
trap stop_after_signal INT TERM

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
  -o "$helper_bin" \
  "$root/helper_main.m" \
  "$root/auth.m" \
  "$root/key_item.m" \
  "$root/fixture_store.m" \
  "$root/fixture_store_syntax.c" \
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
  -o "$parent_bin" \
  "$root/parent_main.m" \
  "$root/auth.m" \
  "$root/exact_helper.m" \
  "$root/bundle_manifest.c" \
  "$root/signing.m" \
  "$root/fixture_store.m" \
  "$root/fixture_store_syntax.c" \
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
  -o "$identity_bin" \
  "$root/identity_dump.m" \
  "$root/signing.m" \
  -framework Security \
  -framework CoreFoundation

set +e
wc -c "$helper_bin" >> "$receipt"
wc -c "$parent_bin" >> "$receipt"
wc -c "$identity_bin" >> "$receipt"
set -e

if [ "$failed" -ne 0 ]; then
  echo "compile_result=failed" >> "$receipt"
  exit 1
fi
echo "compile_result=objects_linked_not_executed" >> "$receipt"
exit 0
