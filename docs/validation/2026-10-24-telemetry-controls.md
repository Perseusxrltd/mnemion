# Product telemetry privacy controls: source acceptance

**24 October 2026, 01:12:30 UTC.** The local privacy-control foundation passed
source qualification. V08 remains **Building**: collection is unavailable, the
destination is null, and no sender or collector is implemented or deployed.
The [full telemetry contract](../implementation/anonymous-product-telemetry.md)
retains its remaining measurement, resource, anonymity and release conditions.

Validation used source `e6e13091893a38c8fb441b094485fbfe589d03d5`, including the
4.46.6 dependency corrections. The 692 declared application, build and test
inputs retained digest
`08b99676591454f12da3a495dca5bff2699a117b91bf1d3680a030b889336881`
after validation. The evidence receipt has SHA-256
`20f9c309fb5c4e9c4911589ea6297859ccca5cedcd8c32c2d4eb585906f43bf7`.
These were private source builds. The signed 4.46.6 security release has its own
frozen source, `a5c3bf29e8feb22d73b4047a13ac93df694dcb0c`, and excludes these
privacy controls.

| Observation | Result and scope |
| --- | --- |
| Persistent native policy and served-app boundaries | 36 focused Python checks passed: policy choices, separate processes, stale enables, restrictive company policy, damaged storage, page serving and existing CSP/private-API boundaries. |
| Browser policy | Seven checks passed, including repeated opt-out invalidating an older enable, denied writes, unavailable coordination and rejection of unsupported fields/disclosure. |
| Desktop bridge | 12 checks passed: two telemetry bridge checks plus ten existing native-operator checks. The shared offline kernel retained the same choice in an independent Python process. |
| Built browser journey | 19 checks passed on the final build: fresh disclosure gate, reload/cross-tab/offline opt-out, empty re-enable, preview, storage loss/corruption, GPC and scrollable mobile controls. Observed page requests stayed on the local fixture origin and made no workspace API calls. |
| Browser policy/fault journey | Eight checks passed for actually served company metadata, company/user precedence, missing Web Locks, denied reads and failed writes with fixed public errors. |
| Build and package contents | Frontend and Electron builds passed. Wheel and source archive contained the same 586-file web bundle and the exact disclosure resource. The actual built wheel executed offline schema/configure/status calls and retained opt-out across separate processes. |

These counts describe overlapping checks of the controls. They do not measure
population anonymity, full product-workflow coverage, telemetry overhead, actual
outbound traffic or all-six-native installed behavior. The wheel was exercised
in isolation on Linux; the complete native installer matrix for this feature
remains required. Test fixtures made no production memory or cloud-model calls.

The first browser journey exposed a delayed checkbox-state change; the control
now shows its pending choice while saving. Short-screen scrolling was also
corrected. The initial failure log remains preserved. A later journey passed,
but its wrapper rejected compact JSON formatting; inspection retained that
wrapper failure and the actual successful observations. The corrected runner
then passed the final browser journeys against the qualified build.

The [app/native guide](../guides/product-telemetry-controls.md) describes the
implemented controls and their limits. Damaged settings suppress collection;
automatic repair is still absent. A failed write does not establish a saved
opt-out. Future collection needs current disclosure, complete ownership and
measurement coverage, bounded sending/cancellation, reviewed ingress and
collector privacy, resource measurements, all-platform acceptance and release.
