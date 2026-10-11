# Native runtime for local app setup

This is an installation dependency under development. It does **not** yet make
Studio able to create a local workspace. Complete setup remains governed by the
[app-onboarding requirements](app-onboarding.md).

The local engine will use PostgreSQL and pgvector, retaining the same role and
space protections as organization-hosted services. Users must not install a
compiler, Python, PostgreSQL or a paid desktop container product to use this path.
The app will download verified packages and retain resumable setup state.

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
outputs, **not signed installer downloads**. Publishing and consuming them
requires the authenticated runtime catalog and app installer still being built.

The matrix builds Linux and macOS x64/ARM64, plus Windows x64. A separate Windows
ARM host runs the actual x64 database under OS emulation. That gate must pass
before offering it, and the app must disclose the engine architecture; the
existing desktop interface remains native ARM64. No ARM database compatibility
claim follows merely from compiling an x64 binary.

## Native acceptance

`deploy/probe_native_postgres.py` extracts the built archive into a new path with
spaces, verifies every inventoried file and checks the executable architecture.
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

## Remaining integration

- Build a portable service/Python runtime, including the selected model drivers.
- Authenticate the catalog and archives before execution; stage atomically,
  enforce disk/resource budgets and resume interrupted downloads.
- Add typed local operator operations for initialization, restricted credentials,
  service/worker lifecycle, recovery and compatible automatic updates.
- Finish Studio's Create, Join, Organization and Recover paths with actual
  readiness checks and actionable retry states. Keep agent operation available.
- Validate the complete flow on every offered platform before release.
