# Release and documentation maintenance

The repository is the source of truth for documentation. The desktop and browser
documentation library bundle the same Markdown under `docs/`, the project README,
security/contribution guidance when present, and the Studio README. Help is
available before server connection. Bundled guides match the installed app;
updating the app updates its guides without an independent content service.

## Required for every release and hotfix

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
   complete set of architecture feeds before a desktop release draft is created.
7. Review the concrete draft and publish only when its documented release gates
   pass. Installed supported desktop packages then receive stable updates under
   the [update policy](service/updates.md).

CI checks can require files and version consistency; they cannot determine whether
prose accurately describes behavior. The person or agent making a change owns the
corresponding documentation review. This workflow does not imply a permanently
running maintainer or promise fixes without an active maintenance session.

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
- [Roadmap](ROADMAP.md): delivered work, priorities and acceptance criteria.
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
