# Bounded operator turns and research watch — 20 October 2026

Source 4.39 combines the [native connector work](2026-10-20-native-connectors.md)
with a real deployment repair and a bounded scientific/tool metadata watch.
The 4.38 candidate is withheld: both container architectures found a missing
canonical-logo input during frontend branding validation. Its immutable source
and failed jobs are retained; their failure is not presented as a release.

## Operator access under continuous scans

The live shared host's guarded upgrade plan repeatedly returned deferred while
managed source scans held shared runtime locks. The new operator context waits
for the existing exclusive lock and announces a temporary scan pause only when
needed. Existing scans retain their lock and finish; no process is killed.
The body runs once, after acquisition. A busy/error result from inside that body
is never retried by this context.

Focused acceptance covers a real shared-lock holder finishing before the
operator enters, exclusive ownership during work, the zero-wait path, bounded
timeout and cleanup, invalid limits, a replacement operator announcement and
the prohibition on replaying a failed body. The existing managed-upgrade cases
retain migration, recovery and current-state behavior. The combined focused run
passed **23 cases**: nine operator-turn, ten managed-upgrade and four research-watch
tests. Runtime and publication
evidence remain separate from these source tests.

## Container correction

The Docker frontend stage now copies `mnemion/assets` before its existing
branding/build check. A separate temporary tree reproducing those branding
inputs passed the canonical asset verifier. There is no local Docker daemon in
this environment; full x64/arm64 image build and real container service checks
remain the release pipeline's responsibility. No gate is bypassed.

## Research watch

The first real collection retrieved **seven of eight sources** and retained
28 metadata candidates after the Crossref query correction. arXiv returned
HTTP 429, which is retained in the generated catalog; direct scientific paper
pages were separately available for the [study](../research/2026-10-20-layered-librarian.md).
This is partial feed availability, not an exhaustive literature survey.

Focused tests verify failure-history retention, arXiv revision deduplication,
rejection of XML entities/untrusted identifiers, safe rendering of hostile
titles, bounded input, and the distinction between a documented Jev model and
a proven stable release. No model was called, account created, trial started,
payment made or dependency adopted. The weekly workflow's actual execution is
a separate check after main receives the implementation.

The complete layered librarian remains planned as R07. A research catalog is
useful infrastructure for that work, not evidence of autonomous consolidation
or a benchmark improvement. The [release status](../RELEASE_STATUS.md) and
[maintenance board](../MAINTENANCE_STATUS.md) report current publication and
GitHub checks automatically.
