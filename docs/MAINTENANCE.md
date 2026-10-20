# Release and documentation maintenance

The repository is the source of truth for documentation. The desktop and browser
documentation library bundle the same Markdown under `docs/`, the project README,
security/contribution guidance when present, and the Studio README. Help is
available before server connection. Bundled guides match the installed app;
updating the app updates its guides without an independent content service.

## Required for every release and hotfix

Keep implementation and documentation current on `main`. Publish fixed version
tags from checked commits. Users must have access to OS/architecture pairs that
are ready while others are tested; a pending architecture is not a reason to hide
a completed published download.

Start each delivery by reviewing current GitHub issues and reports from agents
using Mnemion in real deployments. Recheck the issue inventory before freezing
the release. Bundle as many reviewed, ready bug fixes as the release can safely
carry, and include a validated roadmap improvement when possible. Working
installation, updates, access and memory operations take priority; do not delay
an urgent repair to fill a feature quota. Retain reproduction and acceptance
evidence, map completed fixes to the version below, and leave unresolved or
newly reported failures visible. Passing CI does not invalidate a user's report.

Ship coherent batches of related fixes. During implementation, run focused checks
for changed behavior, then rely on one complete automated release run. Repeat or
broaden local checks only for a failure, a new change or a specific unresolved
risk. Main retains product CI; the full native matrix runs for pull requests,
manual requests and releases, without a duplicate native build on every push.

Use `python -m deploy.release_automation prepare X.Y.Z` after writing release notes
and updating the affected guides/roadmap. It updates package and lock versions,
regenerates both contracts and runs version validation. Commit/push reviewed
source to main, then run `python -m deploy.release_automation start` to freeze that
source and dispatch the full release once. A dirty checkout, source absent from
main, conflicting frozen branch or existing run is handled without a duplicate
build. The [automation guide](implementation/release-automation.md) documents
publication, downstream checks, evidence retention and failure recovery.
For a corrected unpublished release, `start --attempt 2` preserves the first
frozen source and starts a separate attempt. Published releases require a new
version number.

After committing reviewed source, `python -m deploy.release_automation integrate`
handles normal pushes and generated-metadata races without force. Incoming
source changes stop for review. It first runs the pinned local format/lint checks,
without rewriting committed files, so a cheap source failure never reaches main
or starts another CI matrix. Use the locked development environment for both
`integrate` and `start`. `python -m deploy.maintenance_snapshot` gives one
bounded issue/build update; the [maintenance board](MAINTENANCE_STATUS.md) updates
automatically on GitHub issue and workflow events. Use these scripts instead of
repeating manual version edits, job inventories and metadata-only rebase sequences.
Record fully resolved issue numbers in `deploy/issue-releases.json`; the same
workflow labels and closes them only after their release has passed and is
public. Reopened labeled reports remain open. Use
`python -m deploy.issue_releases` for a read-only preview.
For a release session, run `python -m deploy.maintenance_snapshot --watch-seconds 3600`
in the background. It emits only changes after its first observation, reuses
completed failure evidence, checks active jobs once a minute and stops after the
requested duration. It does not retry jobs, edit issues or publish anything.

**Warm native database caches** runs on main each day and when the pinned database
sources or build instructions change. GitHub release branches can read main's
caches; they cannot save a reusable main cache themselves. The warmer calls the
existing native database workflow, including its real relocation, TLS, row-level
permissions, backup and crash checks before saving. Compiler-image and input
fingerprints remain exact; missing metadata or a miss still requires compilation.
The warmer has no signing credentials and publishes no release. It can also be
dispatched manually after a compiler-image change, without rebuilding the app.
Its completion refreshes the maintenance board, which includes warm-up failures
without treating this optional cache as a product publication gate.

The public-upgrade workflow explicitly dispatches status reconciliation after
its platform jobs, including failed runs. Reconciliation waits for the
initiating run to finish before reading its gates. This keeps final upgrade
results and eligible issue closures current without relying on another chained
workflow event. The scheduled reconciliation remains a fallback.

The maintenance board retains failures that finish after a release is published,
including builds of the next version that started earlier. It also inspects active
runs for failed jobs. For a managed-runtime failure, dispatch **Managed runtime
diagnostics** on the affected Mac or Linux runner to check the shared-model
transport and a real API/worker restart without rebuilding desktop installers.
Failed startup fixtures report bounded code locations and exception classes;
private paths, credentials and log messages are excluded. This focused workflow
does not count as a passing product or release gate.

1. Change the canonical version and dependent package metadata/lockfiles together.
   Include both `uv.lock` and `studio/client/uv.lock`, the nested local client
   version in the frontend npm lock, and regenerate the OpenAPI/agent schemas.
   Run `python deploy/release.py` before the expensive build matrix; it checks
   these version boundaries as well as release notes and the roadmap.
2. Add `docs/releases/<version>.md`. Include changes, fixes,
   compatibility/migration impact, verification evidence and known limitations.
   Keep changing publication status in the roadmap and dated validation record;
   a permanent "publication pending" sentence in the packaged notes becomes
   stale as soon as that same build ships. Preserve earlier versions' behavior
   and migration notes when recording completed publication evidence.
3. Review `docs/ROADMAP.md`, set its current distribution and update date, and move
   only verified work into the implemented section. Keep unfinished commitments
   visible; update priorities when evidence changes them.
4. Update each affected setup/API/security/operations guide in the same change.
   Update OpenAPI, the reviewed agent contract and SDK examples when the contract changes. Include relevant
   validation results with the tested version/commit and environment.
5. Run product and native checks. Inspect in-app help on desktop/mobile widths,
   including internal links, code blocks and offline access in the packaged app.
   Release preparation first runs a small preflight with the locked formatter,
   source lint, version/roadmap validation and shell syntax checks. The full
   product/native matrices start only after it passes, avoiding wasted platform
   compilation when a cheap source check fails. Preflight does not replace the
   complete regression, installed-app, signature or update gates.
   Native database source downloads allow three attempts for transient DNS,
   connection, timeout and selected HTTP failures, with two- and four-second
   backoffs. Each attempt verifies the pinned digest and size limit; certificate,
   integrity and permanent HTTP failures stop immediately. Partial-file cleanup
   applies only to the current download's own file.
   Desktop packaging also retries once when Electron's downloader reports HTTP
   500/502/503/504. Compilation, signature/integrity, disk-space and other
   failures stop immediately. The actual build exit status remains the gate;
   package verification and installed-app checks still run normally afterward.
   Native focus scenarios must establish a visible, restored, focused window
   before testing foreground restart protection. Windows GUI probes must be
   allowed to show their window; a hidden startup can report focus without
   visibility. Retain actual window states around the guard check, and keep
   hidden/minimized background behavior covered separately.
6. Prepare immutable, signed and verified artifacts and update feeds. The release
   verifier requires matching versions, release notes, a current roadmap and a
   complete set of installers and update feeds for each OS/architecture selected
   in `deploy/release-targets.json` before a desktop release draft is created.
   From 4.0.6, run `python deploy/bundle_studio.py` before `uv build`. The verifier
   also inspects both Python formats for identical web Studio files, matching
   version, bounded paths/sizes, hashes and dependency notices. The generated
   `mnemion/_studio/` is packaged but not committed. All frontend builds require
   the essential offline guides and the current release notes, including Docker.
   From 4.0.7, product CI also runs real API/worker Supervisor crash and shutdown
   checks on native macOS Intel/ARM64, in addition to the Linux service matrix.
   The dependency audit includes the optional supervision runtime. From 4.0.8,
   both native Macs and Linux 3.12 also perform real signed managed-service
   installation, rollback and accepted-write preservation. Font assets and
   their SIL licenses are part of the frontend inventory.
   The service suite enforces at least 75% coverage of `mnemion.service`;
   the retained legacy suite independently enforces at least 45% of the rest
   of `mnemion`, using `deploy/legacy.coveragerc`. This keeps changes to either
   implementation from diluting the other suite's coverage measurement.
   The non-service suite also measures CLI/connection modules outside
   `mnemion.service`. Keep their unit tests under `tests/` so this gate counts
   the exercised code; running those tests only in `service_tests/` cannot
   satisfy the separate non-service measurement. Do not lower the threshold
   to accommodate a misplaced test.
   Intel Mac CI builds the current locked `cryptography` from its verified source
   with static OpenSSL pinned in `deploy/intel-crypto.json`. The builder verifies
   its architecture, absence of non-system dynamic libraries and Ed25519 operation,
   bundles licenses/provenance and then runs the actual managed upgrade/rollback
   against that wheel. Review OpenSSL and Python dependency advisories whenever
   changing those pins. Compiler tools and publisher keys never reach managed
   hosts; the signing step is separate from dependency compilation.
   Assemble `service-update.json` from the exact wheel, source, lockfile and
   migrations and the Intel dependency using `python -m deploy.service_update_manifest sign --artifacts
   release-artifacts --commit COMMIT`. The dedicated private key is supplied
   only through the reviewed signing environment. The release verifier checks
   the signature, input parity and hashes before creating a draft.
7. Publish only when the concrete draft's documented release gates pass.
   [Verify uploaded release artifacts](../.github/workflows/verify-artifacts.yml)
   runs automatically after a successful release-preparation workflow. It checks
   every uploaded byte on a separate GitHub runner, invokes the production
   signature/feed/package validator from the exact release commit, and rechecks
   the asset IDs, sizes and digests afterward. GitHub requires repository push
   access to discover unpublished drafts, so this job needs `contents: write`
   and `actions: read`. Its verification job only reads/downloads releases, receives no
   signing keys, and strips GitHub credentials from the source validator's
   subprocess environment. Neither checkout persists credentials. Download
   its small `verified-release-artifacts` receipt instead of downloading every
   installer again on the operator's computer. The receipt's source, release run
   and asset inventory must match the concrete draft; do not reuse a receipt
   after replacing draft assets. The workflow also accepts a completed release
   run ID for manual verification of a draft or already published release.
   After automatic verification, a separate publication job checks the completed
   source, main ancestry, current asset inventory, tag and latest stable version.
   It publishes the unchanged draft and explicitly starts website and complete
   public-upgrade checks; token-based publication alone does not trigger release
   events. It commits bounded publication/verification receipts on main. Manual
   verifier dispatch stays read-only. The status reconciler retains each version's
   observed gates and scope counts under `docs/validation/releases/` automatically.
   Its [validation record](validation/2026-10-12-artifact-verification.md)
   distinguishes guard tests from actual hosted verification. Installed
   supported desktop packages receive stable updates under the
   [update policy](service/updates.md).

Update the release-target version with every patch. Add a new architecture only
after its native installation/update checks pass. Keep update feeds for every previously
published OS/architecture pair in each new stable release, because installed clients follow
the latest stable channel. Never replace a published binary in place.

CI checks can require files and version consistency; they cannot determine whether
prose accurately describes behavior. The person or agent making a change owns the
corresponding documentation review. This workflow does not imply a permanently
running maintainer or promise fixes without an active maintenance session.

## Automatic product-page updates

The [Perseus XR product page](https://www.perseusxr.com/mnemion) reads published
stable releases directly. Version labels, available architectures, installer URLs,
checksums, release notes and version-specific guides follow the same release.
The roadmap link follows `main`, so planning updates are visible between releases.
Do not edit or redeploy the website for an ordinary hotfix.

The main download recommends a published OS/processor pair using local browser
hints. When the browser withholds the processor type, visitors choose it; all
available installers remain in an expandable section that works without
JavaScript. The recommendation always uses the same verified release metadata.

`.github/workflows/website-release.yml` maintains `deploy/published-release.json`
using the same bounded metadata fetcher as public update rehearsals. GitHub
gateway errors (502/503/504) get two retries with one- and two-second backoffs
inside the original 45-second transfer budget. Redirect, approved-host, size,
credential-separation and checksum checks remain enforced. Other HTTP errors
and certificate failures are not retried. This corrects the observed checksum
gateway timeout during 4.1.2 publication without hiding an integrity failure.

The workflow maintains this fallback
after release publication or edits, with a six-hour reconciliation schedule and a
manual dispatch for recovery. It verifies GitHub's uploaded-asset SHA-256 digests
against the published `SHA256SUMS.txt`, rejects drafts and older generations, and
requires each offered installer's update assets. Only changed metadata is committed
to `main`; the Actions token prevents a build loop. Concurrent changes are rebased
without force pushes. The manifest never moves backwards in version.

The website caches both the GitHub API and this independent raw-content manifest
for five minutes. It chooses the newest valid release, keeping a bundled published
snapshot only as a final fallback. An authenticated repository release webhook
invalidates the release cache, product page and sitemap immediately; it cannot
supply page content or arbitrary invalidation paths. Its signing secret belongs
only in the repository webhook configuration and the website's production
`MNEMION_RELEASE_WEBHOOK_SECRET`, never in this repository.

To recover a missed metadata event, run the **Synchronize public release metadata**
workflow. A future publisher that uses `GITHUB_TOKEN` must explicitly invoke this
workflow as part of publication: GitHub does not recursively trigger workflows
from that token's release events. The scheduled reconciliation is a second path.
The workflow must also exist in the released tag. The already-built 4.0.1 tag
predates this setup, so its initial synchronization was dispatched once during
installation; subsequent release commits include the workflow automatically.
Check the workflow result and repository webhook delivery status for failures.
These tasks use standard public GitHub Actions and the existing website; they
require no model calls, paid runner, new hosting service or routine deployment.
Release-note accuracy and roadmap completion remain part of the code review and
release gates; automation must never invent a completed feature.

## Public desktop upgrade checks

`Public desktop update rehearsal` installs a previous **unmodified, published**
installer on fresh GitHub-hosted Windows, Mac and Linux runners. It waits for the
real default startup check and system-inactivity guard, then verifies a new
target-version process and preserved profile/preferences. It uses official feeds
and the embedded production keys, with no rewritten app entry point, debugger,
fixture key or simulated idle time. It adds no sandbox-disabling flag and records
the packaged Linux launcher's actual flags. Linux runs use Openbox so normal
minimize/focus behavior works; Xvfb alone is not a desktop window manager.
From 4.0.4, Linux registration stays at its production default and the observer
checks that the login entry targets the actual installed update. Mac/Windows
login registration remains disabled on the disposable runners. Checking a
registration file does not certify a full reboot/login sequence.

The workflow runs after publication for release tags that include it, or manually
with the current public tag. The first 4.0.2 run requires manual dispatch because
its release commit was already frozen before this workflow was added. Every
selected architecture needs an earlier public installer; newly introduced
architectures retain their native fixture gate until their next public upgrade.
Only small JSON results and bounded logs are retained for seven days. Failures
are visible in Actions and need investigation; they do not silently alter,
withdraw or republish immutable release artifacts.

For an unexplained Linux restart stall, `Linux updater developer diagnostic`
provides a separate manual investigation. It verifies and copies the public
AppImage on fresh hosted runners, extracts it, and enables only the copied
Electron binary's loopback inspector fuse. The ASAR code, feeds and restart
guards remain unchanged. The recorded hashes distinguish the instrumented copy
from the public installer. Bounded snapshots report Electron and X11 inactivity,
window state, and whether the renderer can answer its draft/transfer safety
check. Inspector attachment and extraction can affect timing; this workflow is
**never evidence that a public automatic upgrade passed**. Its helper is not
included in the desktop application. After a justified fix, use the ordinary
unmodified public rehearsal for acceptance.

The diagnostic's `timers` experiment compares four fresh runners: each Linux
architecture with the original timer references and with referenced timers.
Both copies add the same bounded trace inside the existing restart callback;
the comparison changes only whether those timers keep Node's loop scheduled.
It uses no debugger, fake inactivity or changed safety predicate. Passive
process/filesystem observations record the eventual version and installed bytes.
These modified ASAR copies remain developer experiments, never public-release
acceptance evidence.

The `launch` comparison keeps the original timers and traces their actual restart
guard values on both an extracted copy and a mounted diagnostic AppImage. The
latter retains the verified public runtime prefix and repacks only a private
copy of its filesystem. Both launch paths use real inactivity and production
feeds, without a debugger; neither modified copy is public acceptance evidence.

The `focus` experiment compares the original focus flag with a guard that treats
only a visible, restored window as focused. Both mounted copies record the raw
focus, visibility and minimized state; real inactivity, renderer safety and
transfer checks remain unchanged. This isolates stale window-manager focus
reports without claiming that an active window may be interrupted.

The runner has no user workspace, production memory credentials or signing
secret. Native fixture checks still cover cancellation, malicious updates,
interrupted downloads and restart guards before publication. The public rehearsal
adds deployment evidence; neither check substitutes for the other.

## Release service costs

The product is [free forever](SUPPORT.md), including team features and updates.
Keep support payments separate from downloads and product access. The website
may offer optional one-time PayPal support from €5; its verified recipient belongs
in deployment configuration, not in public source or application telemetry.
Do not claim that PayPal has no fees or transfers automatically to a bank.

Project release work is restricted to free services. Do not enter payment details,
purchase certificates or enroll in paid programs. Avoid trials that automatically
convert to paid plans; if a trial is encountered, cancel it before any charge and
retain confirmation privately. Do not change unrelated user subscriptions.
Provider account details, private keys and enrollment evidence stay outside Git.
This restriction does not promise that an organization's chosen hosting, storage
or optional model providers are free; administrators control their own services.

Routine native validation runs on standard public-repository runners and keeps
results in job logs; it does not upload installer artifacts. Release-only artifact
transfers expire after one day. Before enabling a signed release, verify that its
temporary storage fits the account's remaining free allowance and delete staging
artifacts after successful assembly. A failed assembly retains its transfers for
a retry, with a maximum one-day retention; remove abandoned transfers promptly.
The source builder's control files stay outside the release asset directory.
Published release-note links are converted to the matching immutable Git tag.
A successful public build does not establish the billing
status of unrelated account usage. Never enable larger paid runners or raise a
storage/billing limit to make a check pass.

## Documentation map

- [Quick start and API](service/README.md): install, initialize, connect and use.
- [Deployment](service/deployment.md): service, workers, storage and operations.
- [Organizations](service/organizations.md): identities, spaces and security.
- [Sources](service/connectors.md): local, Git, cloud and messaging adapters.
- [Git journals](service/git-journal.md): opt-in native-memory publication, retained-history consent and source replay.
- [Agents](service/agents.md) and [capture](service/capture.md): platform integration.
- [Knowledge](service/knowledge.md): wiki, graph and review workflows.
- [Insights/evaluations](service/insights.md): monitoring, metrics and experiments.
- [Migration](service/migration.md) and [recovery](service/recovery.md): continuity.
- [Updates](service/updates.md) and [Studio](../studio/README.md): desktop lifecycle.
- [Code signing](CODE_SIGNING.md) and [privacy](service/privacy.md): distribution
  trust, release responsibilities and data handling.
- [Roadmap](ROADMAP.md): delivered work, priorities and acceptance criteria.
- [Librarian](service/librarian.md): model configuration, budgets, proposals and recovery.
- [Free forever and support](SUPPORT.md): free access and optional contributions.
- `docs/releases/`: immutable per-version release notes.
- `docs/validation/`: dated evidence and its limitations.
- `docs/implementation/`: feature preservation and technical decisions.
- `docs/research/`: original product/competitor study and supporting evidence.
- `docs/legacy/`: archived material; it is not current setup guidance.

## Support and security reports

Use [GitHub issues](https://github.com/Perseusxrltd/mnemion/issues) for reproducible
bugs and feature requests. Include versions, OS/architecture, sanitized logs and
steps; omit credentials and private memory content. Follow the repository
[security policy](../SECURITY.md) for vulnerability reports.
