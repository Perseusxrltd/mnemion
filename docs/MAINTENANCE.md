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
   Update OpenAPI and SDK examples when the contract changes. Include relevant
   validation results with the tested version/commit and environment.
5. Run product and native checks. Inspect in-app help on desktop/mobile widths,
   including internal links, code blocks and offline access in the packaged app.
6. Prepare immutable, signed and verified artifacts and update feeds. The release
   verifier requires matching versions, release notes, a current roadmap and a
   complete set of installers and update feeds for each OS/architecture selected
   in `deploy/release-targets.json` before a desktop release draft is created.
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
