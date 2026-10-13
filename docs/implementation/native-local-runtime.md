# Native runtime for local app setup

Version 4.0.11 bundles this runtime and includes guided local workspace creation.
Each published installer must pass the complete installed-platform gates.
Earlier 4.0.10 connects to an existing service. Complete setup is governed by the
[app-onboarding requirements](app-onboarding.md).

The local engine uses PostgreSQL and pgvector, retaining the same role and
space protections as organization-hosted services. Users must not install a
compiler, Python, PostgreSQL or a paid desktop container product to use this path.
Installers bundle verified runtime packages; the app downloads the selected
model and retains resumable setup state.

## Database package

`deploy/native-postgres.json` pins PostgreSQL 18.6, pgvector 0.8.7, OpenSSL 3.5.9
and zlib 1.3.2 to reviewed upstream sources and SHA-256 digests. The native
builder checks those bytes, restricts extraction, compiles with portable CPU
options and includes upstream licenses. OpenSSL and zlib are linked statically;
the package retains verified TLS and gzip recovery support. ICU and optional
external authentication/build integrations are disabled. New local databases
use PostgreSQL's built-in Unicode locale; importing a database with unsupported
collation/provider requirements needs a compatibility check before restoration.
The Unix build records one source adjustment: PostgreSQL's libpq symbol check
allows OpenSSL's `pthread_exit`, which terminates a thread, and Apple's `_atexit`,
which registers cleanup. Its checks for process-exit calls remain active; the
original substring check rejects these symbols when OpenSSL is linked statically.

The build produces a ZIP containing tools, extension SQL, time-zone data and a
file inventory. Paths are relocatable; no system database installation is
overwritten. Mac executables use ad-hoc signatures for local integrity, which
does not establish Apple publisher trust. These CI archives are development
outputs, **not signed installer downloads**. The desktop builder verifies their
inventories and source provenance before bundling them into its authenticated
installer/update artifacts; see [native packaging](native-desktop-packaging.md).

The matrix builds Linux and macOS x64/ARM64, plus Windows x64. A separate Windows
ARM host runs the actual x64 database under OS emulation. That gate must pass
before offering it, and the app must disclose the engine architecture; the
existing desktop interface remains native ARM64. No ARM database compatibility
claim follows merely from compiling an x64 binary.

The Windows database runtime requires Windows 10 version 1903 (build 18362) or
later, including Windows 11. Every packaged executable selects a UTF-8 active
code page through its application manifest so narrow Windows arguments and
filesystem calls preserve Unicode workspace paths. Earlier Windows builds
ignore that setting. The builder merges existing manifest settings, verifies
the embedded resources, and inventories the resulting bytes before packaging.

## Reusing a verified database build

Desktop checks call the database workflow for every relevant push and pull
request. Direct database dispatch remains available; a second independent
compiler matrix is no longer started for the same push.

The database workflow can reuse an exact archive from this repository's normal
GitHub Actions cache. The key includes the operating system, CPU architecture,
runner image name and version, Python patch version, pinned dependencies, native
builder, Windows manifest and workflow instructions. A changed input or missing
runner image metadata takes the ordinary compilation path. There are no partial
cache matches. This avoids repeating compilation when application-only changes
leave those inputs unchanged; it is not a reproducible-build claim.

Only the main branch saves an archive, after the full database probe passes.
Main and release branches may restore it; pull requests compile independently.
Only the ZIP enters the cache. Database contents, credentials, signing keys and
old probe receipts are excluded. Cache capacity and billing settings are not
changed; eviction simply requires a fresh build.

Every restored archive must pass fresh inventory and pinned-source checks before
its binaries run, then complete the same TLS, permissions, vector, backup and
crash-recovery probe. Windows ARM still runs the actual x64 database under
emulation. Every release still builds, signs and tests its application packages.
A bad cached archive fails validation; a maintainer can remove that exact cache
entry and rerun to compile again. No release gate is skipped after a cache hit.

The cache and archive tests passed **37 checks** on 2026-10-13. Hosted cold-build
and cache-hit measurements remain pending; no speedup has yet been measured.

## Native acceptance

`deploy/probe_native_postgres.py` extracts the built archive into a new path with
spaces and accented characters, verifies every inventoried file and checks the
executable architecture.
It initializes a private temporary database in a path with accented characters,
uses SCRAM credentials over certificate-verified loopback TLS, and tests vector
search and row-level read/write isolation. It creates a gzip-compressed backup,
restores into a separate database and checks both after an immediate shutdown
and restart. It stops and removes only its disposable cluster. Credentials never
enter build artifacts, command-line arguments or evidence output.

`.github/workflows/native-runtime.yml` records those native checks. Ubuntu 22.04
builders establish the Linux binary baseline; a successful local build on a
newer Linux distribution does not establish that baseline. The checks do not
replace a full clean-machine app/service/model/onboarding walkthrough.

The 2026-10-11 matrix passed the four Unix database targets. The Windows build
produced the pinned database and static OpenSSL archive, but its earlier probe
failed when `initdb` entered its restricted token
([run](https://github.com/Perseusxrltd/mnemion/actions/runs/38121287783)).
Elevated processes can create Administrators-owned files, while PostgreSQL
removes that group's access before initialization. An owner-rights ACL therefore
cannot reliably protect a local workspace and keep it accessible to the engine.

Private directories and exclusive output files now atomically name the creating
TokenUser as owner and grant access to that SID. New database children inherit
the user-only directory ACL. Existing foreign-owned or redirected folders remain
rejected; the app does not take their ownership. The native probe creates its
temporary root and secret files through these production helpers.

Fast Windows x64 and ARM64 jobs check private state, persisted RAM settings and
actual `CreateRestrictedToken` access before database compilation begins. They
disable Administrators and Power Users with maximum privileges removed, verify
those groups no longer grant access, and read/execute both inherited and explicit
private files while impersonating the restricted token. They also check folder
traversal and new child-file creation. The rerun passed both Windows private-state gates and the two Linux database
probes. Windows initialized its database, then exposed a separate output-pipe
hang when `pg_ctl` launched a server. Native launchers now capture output in
private regular files, with bounded reads, so a descendant cannot keep Python
waiting for pipe EOF; production and probe share this helper. The probe also
canonicalizes the system temporary parent for macOS's `/var` alias and uses the
production sequence of precreating/rechecking the private data directory.
The corrected matrix passed all four Unix targets. Windows then reached its
identity check and exposed ANSI conversion of the accented data directory;
UTF-8 executable manifests corrected it. A retained Windows build with those
manifests passed the complete probe locally, including accented executable and
data paths. The complete rebuilt matrix subsequently passed in
[run 38132099847](https://github.com/Perseusxrltd/mnemion/actions/runs/38132099847)
at `95faa444056009518248baecf71aa6c1ee873f14`: Linux and macOS x64/ARM64,
Windows x64, and the same Windows x64 package under ARM64 emulation. Both
Windows private-state gates passed before compilation. This establishes native
database package acceptance; complete app installation and update flows remain
separate gates.

## Remaining integration

The published 4.1.7 release passed installed local setup/reopen and public
automatic upgrades on all six desktop targets; see the
[release evidence](../validation/2026-10-13-managed-update-schedule.md).
The 4.2.0 personal sign-in migration has separate
[validation and publication requirements](../validation/2026-10-13-individual-sign-in.md).

- Extend the existing typed initialization, lifecycle, RAM recovery and local
  address commands to the remaining host/source/backup workflows.
- Complete organization-managed hosting, provider sign-in and recovery entry
  points with actionable retry states and equivalent agent operations.
- Extend the hardware, supported OS-version and restricted company-device
  matrix, retaining the complete installed gates for every offered platform.
