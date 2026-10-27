# Telemetry catalog compatibility — 27 October 2026

Source follow-up based on `ca2d3fbcb3292a269f389b46c4f58ea425db90b1`.
**Scoped compatibility checks passed; full telemetry acceptance remains open.**
This follow-up adds dedicated categories for the two previously unmeasured
classic CLI paths while preserving stored meanings across catalog versions.

The [catalog](../../mnemion/product_telemetry/catalog.json) now uses an explicit
workflow order: `capture.split` and `models.test` follow the original 94 IDs.
[Python decoding](../../mnemion/product_telemetry/catalog.py) and the
[native/browser decoder](../../studio/electron/telemetry-catalog.ts) use this
order so existing numeric cells and contribution-budget scopes retain their
meaning. This is catalog version 2, not a new telemetry packet version.

The [browser queue reader](../../studio/frontend/src/workspace/telemetry-aggregate.ts)
accepts valid v1 data without rewriting it on inspection. The next collection
write uses v2 while retaining valid existing entries and contribution counts
under the same limits. A queue labeled v1 cannot contain the newly appended workflow
cells or contribution scopes. Saved policy, spending and privacy fences remain
authoritative; the change provides no new allowance.

[Wire v2](../../mnemion/product_telemetry/wire-v2.json) retains four-byte packets,
view IDs, domains, weights and existing numeric meanings. New closed aggregates use
report schema 4 with the appended feature labels. The
[publisher validator](../../mnemion/product_telemetry/publication.py) continues
to read immutable schema 1–3 reports with their original 94 feature labels plus
`unobserved`; it does not relabel or extend historical reports.
A schema-3 feature report generated from the immutable base source using
4,096 synthetic automatic packets remained byte-identical after reopening
with the new publisher. This fixture used no network or real usage data.

The [classic CLI map](../../mnemion/product_telemetry/cli-origins.json) declares
split apply as `capture.split`, with an unconfirmed outcome; dry-run stays
excluded. `models.test` uses the existing command's exact trimmed `MNEMION_OK`
success condition and failed outcomes. The owner sees the command outcome,
not prompts, replies, model identifiers, input paths or output contents.
The shared installation choice, invocation-only suppression, nested ownership
and absence of a CLI sender/keepalive remain unchanged.

The regenerated inventory maps **96 of 96 categories** and lists **701 action
rows: 398 mapped, 295 excluded, eight delegated and zero unmeasured**. Classic
CLI contributes 64 rows: 34 mapped and 30 excluded. These are reviewed
declarations, not proof of every call site, autonomous workflow or installed
runtime. The preceding catalog-v1 checkpoint remains historical: 94 mapped
categories and 700 rows comprising 396 mapped, 294 excluded, eight delegated
and two unmeasured. Earlier dated coverage and failed evidence remain retained.

The final selection passed **322 distinct checks**, with no failures or skips:

| Checks | Passed | Duration |
| --- | ---: | ---: |
| Python catalog compatibility, actual classic dispatch, coverage, aggregates/publication and wire | 175 | 38.02 s |
| Browser-source choice/client/delivery/review/inspection, including old-queue budget preservation | 136 | 9.43 s |
| Native wire, including old-packet identity and exhaustive cross-language encoder parity | 10 | 0.72 s |
| Native SQLite/Python store upgrade | 1 | 0.87 s |

The [compatibility tests](../../tests/test_product_telemetry_catalog_compatibility.py)
and retained logs record these scoped results. The Electron build and frontend
typecheck also passed. No model/provider calls or network collection occurred;
the immutable 4.46.40 release was not altered.

The final selected manifest covers **866 files**, digest
`a3ef4414434098400462f59b31b9971b49041c2e9d07aedc84bda69aab3852ea`.
The native SQLite upgrade case was added after the initial manifest;
`additional-test-input.json` verifies that only its test file changed and that
it then passed. Application inputs and other qualified tests were unchanged;
those groups were not repeated or counted again. Final version-only release
metadata binding remains a separate pending step.

All 66 requirements and **V08 Building** remain unchanged. Production
collection/destination/route stay **false/null/null**, with empty release CAs.
The existing **2 MiB / 0.5%** resource ceilings and failed results remain binding.
No installed/native/browser journey, resource saving, provider/privacy
qualification, production activation or full telemetry acceptance is claimed.
Normal 4.46.41 preparation changed only eight selected input files by exact
version replacements. The 866-file release input digest is
`33106a06d68758c28510e61d71fb093b9286a672e637af086775f637ca2c27f6`;
runtime behavior and the qualified checks are unchanged by those replacements.
See the [acceptance ledger](2026-10-27-telemetry-acceptance-ledger.md) for the
remaining gates.
