# Contributing to Mnemion

Mnemion is a free shared-memory platform for people, organizations and agents.
Current implementation and documentation live on `main`. Submit external changes
as pull requests against `main`; maintainers keep release fixes and guides current
there. Published versions use immutable tags and artifacts.

## Development

Use Python **3.12–3.14**, Node.js **22**, and the committed dependency lockfiles.
Use Python 3.12 for the optional Chroma-based legacy compatibility tests.

```sh
git clone https://github.com/Perseusxrltd/mnemion.git
cd mnemion
python -m pip install uv==0.12.24
uv sync --locked --group dev --python 3.12
npm --prefix packages/client ci
npm --prefix studio/frontend ci
npm --prefix studio/electron ci
```

Service integration tests require PostgreSQL with pgvector; the exact disposable
service setup and environment are in `.github/workflows/ci.yml`. Never run
integration or migration fixtures against a user's real database or vault.

```sh
uv lock --check
uv run ruff check .
uv run ruff format --check .
uv run python -m pytest service_tests client_tests -q
npm --prefix packages/client test
npm --prefix studio/frontend run build
npm --prefix studio/electron test
```

Install the `legacy` extra before running `tests/`; the service does not require
Chroma by default. Unit tests use synthetic fixtures. Real-model checks explicitly
opt in to a pinned model download/cache and need adequate resources. Use bounded
CPU/memory and do not run a large model merely to check a small change. API keys
and paid model calls are not required by the normal test suite.

Native desktop checks build and launch each OS/architecture on its own runner.
Use [Studio](studio/README.md) and [Windows validation](docs/windows-release.md)
for local packaging. Build-only artifacts must not be presented as user releases.
The first desktop release targets Mac and Linux; Windows release work continues.

## Architecture and review

- Preserve canonical source text, evidence and revision identities. Derived titles,
  summaries, links and librarian findings remain reviewable proposals.
- Enforce organization/space permissions at the service boundary and in retrieval,
  exports, jobs and derived views. Unknown or deleted data must not bypass policy.
- Respect durable deletion, revocation and quarantine. Recovery must reconcile
  newer denials; do not resurrect a memory from an older backup.
- Keep model calls optional, bounded and explicitly approved for outbound data.
  A model's finding does not automatically verify, merge or delete facts.
- Preserve Obsidian paths, links and personal annotations during managed refresh.
- Use small dependencies and update locks, notices and security review when needed.
- Run checks relevant to the change and the required release checks; do not claim
  capacity or model accuracy from synthetic tests.

Use conventional commit messages. Update affected setup/API/security guides,
release notes and the [roadmap](docs/ROADMAP.md) with each product change. Follow
[release maintenance](docs/MAINTENANCE.md), including complete per-platform update
assets, the no-spend policy, and protected signing keys. Never commit credentials,
private data, model weights, temporary databases or browser profiles.

The current benchmark protocol and measured limitations are linked from
[the reproduction guide](benchmarks/README.md). Historical v3 comparisons are
preserved separately and are not measurements of the rebuilt service.

Report bugs and proposals through [GitHub issues](https://github.com/Perseusxrltd/mnemion/issues).
Follow [SECURITY.md](SECURITY.md) for private vulnerability reports. Contributions
are distributed under the repository's MIT license.
