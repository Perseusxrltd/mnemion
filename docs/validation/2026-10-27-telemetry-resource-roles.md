# Telemetry resource process-role controls — 27 October 2026

This source follow-up, prepared on base
`0dd5999652236ceeda7e7acd753c29c5cc2bf5c5`, corrects diagnostic controls.
Focused checks passed; the selected changed-source measurement is pending.
No new resource result is credited here.

## Retained finding

The [original metadata-allocation diagnostic](2026-10-27-telemetry-metadata-allocation-results.md),
run `40416923461` on source `192b0df98644b845fd3117516ec9d42c4167acfa`,
recorded two Electron `Tab` processes in `r1-enabled` and one in every other
case. Their exact identities were not recorded. The old probe requested
DevTools closure without waiting for its lifecycle to finish, but this does
not establish that the second process was DevTools or explain the observed
resource differences.

All six original cases, ambiguous renderer comparison and failed resource
qualification remain retained. Profiled observations establish neither a
causal regression nor production-only telemetry overhead.

## Diagnostic changes

- [Development startup](../../studio/electron/application.ts) honors
  `MNEMION_STUDIO_DEVTOOLS=0` before opening DevTools. The diagnostic sets this
  explicitly; normal packaged startup is unchanged.
- The [app probe](../../studio/electron/scripts/probe-telemetry-renderer.mjs)
  matches the app window's OS process ID to Electron's single `Tab` process in
  every sample. Missing or extra renderers, additional windows or open DevTools
  reject the sample. Numeric web-content process mappings and fixed content types
  remain in failed samples for investigation, without recording their titles or
  URLs. Other process roles remain recorded.
- The [report reader](../../deploy/report_telemetry_renderer.py) independently
  checks those numeric identities against process rows and requires stable
  app main/renderer identities across comparison samples. It retains transient
  processes that appear only between the first and last samples, makes incomplete
  CPU accounting explicit, and reports CPU differences for each comparable role.
- The [existing probe](../../deploy/probe_telemetry_renderer.py) adds a separate
  `--comparison` mode without allocation attribution. It retains 128 real
  memory cycles per case, in the fixed order `r1-unavailable`, `r1-opted_out`,
  `r1-enabled`, `r2-enabled`, `r2-opted_out`, `r2-unavailable`. Each comparison
  uses its own triplet's unavailable baseline. Process sampling remains active;
  allocation attribution is a separate, mutually exclusive mode.

The report regression selection passed **15 tests**. A separate private
verification selection passed one valid case and rejected eight invalid cases,
including an extra/replaced renderer, debugger, missing ownership or phase,
extra window, boolean PID and enabled allocation attribution. Re-reading the
original six-case artifact preserved every earlier result and comparison.
The Electron build, Python lint and Node probe syntax checks passed.

One changed-source comparison through the existing diagnostic pipeline is
selected after source review. There is no forced GC, warmup, idle padding or
reduced workload. Source matching, process ownership across the six actual app
cases, cleanup and measured RSS/CPU outcomes are still pending. No persistent
SQLite handle or positive permission cache is introduced by this follow-up.

The **2 MiB added RSS / 0.5% of one core** ceilings remain unchanged. This
diagnostic correction provides no resource saving, installed-platform or
provider/privacy acceptance. All 66 requirements and their states remain
unchanged; V08 is **Building**, production collection is `false`, destination
and route are `null`, and release certificate authorities remain empty.
