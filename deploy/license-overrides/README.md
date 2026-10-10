# Version-bound license copies

The locked `tokenizers`, `loguru`, and `flatbuffers` Python wheels do not include
their license text. These copies come from the corresponding verified source
archive or immutable upstream release commit. `manifest.json` records the exact
version, source, archive/member where relevant, and SHA-256 of each original file.
The original text has not been edited.

`deploy/notices.py` verifies these hashes and uses a copy only for its exact
package/version when the installed distribution has no license file. A dependency
update cannot silently reuse an older override. Recheck upstream licensing and
bundled notices when refreshing one of these dependencies.

`native-python.json` covers the reviewed Linux standalone CPython 3.13.16 used
for local desktop validation. Its native libraries are embedded in `libpython`,
so a wheel inventory alone misses them. The catalog matches the actual runtime
binary's SHA-256 and selects notices from the verified full upstream archive for
its actual built-in modules. It records archive/member hashes and the immutable
build-source revision. Berkeley DB and Tk are absent from this binary's built-in
modules and from the packaged helper; their licenses are not included as if those
components had shipped.

Unrecognized Python runtimes that embed TLS or compression libraries fail desktop
notice collection. Standard CPython installations retain their own license files;
native release review must also inspect any separately bundled system libraries.
The generated CycloneDX file is a package inventory, not a complete operating
system or binary-composition scan.
