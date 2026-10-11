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

1. Change the canonical version and dependent package metadata/lockfiles together.
2. Add `docs/releases/<version>.md`. Include the shipping status, changes, fixes,
   compatibility/migration impact, verification evidence and known limitations.
   Do not overwrite an earlier version's release notes.
3. Review `docs/ROADMAP.md`, set its current distribution and update date, and move
   only verified work into the implemented section. Keep unfinished commitments
   visible; update priorities when evidence changes them.
4. Update each affected setup/API/security/operations guide in the same change.
   Update OpenAPI, the reviewed agent contract and SDK examples when the contract changes. Include relevant
   validation results with the tested version/commit and environment.
5. Run product and native checks. Inspect in-app help on desktop/mobile widths,
   including internal links, code blocks and offline access in the packaged app.
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
7. Review the concrete draft and publish only when its documented release gates
   pass. Installed supported desktop packages then receive stable updates under
   the [update policy](service/updates.md).

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

`.github/workflows/website-release.yml` maintains `deploy/published-release.json`
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
