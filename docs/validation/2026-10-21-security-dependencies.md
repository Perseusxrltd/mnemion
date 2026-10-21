# Security dependency hotfix validation

Recorded 21 October 2026 for a prepared, unreleased stable hotfix. The dependency
change removes the vulnerable Certifi and Pillow versions reported by
[CI run 39527490005](https://github.com/Perseusxrltd/mnemion/actions/runs/39527490005),
which found nine known advisories in two packages.

- **Certifi 2026.7.22 → 2026.10.19:** the root service and desktop build require
  `certifi>=2026.10.19`. [PYSEC-2026-4320 / the Certifi advisory](https://github.com/certifi/python-certifi/security/advisories/GHSA-6q48-6c7w-9gw2)
  describes compromised intermediate CA keys in an emSign trust chain, allowing
  an on-path attacker to intercept or modify TLS traffic. The selected release
  excludes the affected trust roots and retains the unaffected roots restored
  in 2026.10.19.
- **Pillow 12.3.0 → 13.0.0:** the root service requires `pillow>=13.0.0,<14`.
  All eight Pillow advisories reported by CI identify 13.0.0 as fixed; the
  [version's PyPI advisory metadata](https://pypi.org/pypi/pillow/12.3.0/json)
  and original audit are retained with the evidence.

## Installation constraint

The pinned [FastEmbed 0.9.0 metadata](https://pypi.org/pypi/fastembed/0.9.0/json)
still declares `Pillow<13`. Mnemion explicitly selects the patched version with
`override-dependencies = ["pillow>=13.0.0,<14"]` under `[tool.uv]`; both lockfiles
retain the relevant security floors. This dependency change keeps FastEmbed,
the text encoder code, pinned model weights and model generation identifiers
unchanged.

Use the documented [locked uv setup](../../README.md#run-the-service) for source
installations, or official installers for published releases. Ordinary
`pip install` does not apply uv overrides and cannot resolve the upstream
`Pillow<13` constraint together with Mnemion's `Pillow>=13` requirement.
The override is an explicit installation constraint, not a claim that upstream
FastEmbed has declared Pillow 13 compatibility.

## Measured evidence

| Check | Result | Scope |
| --- | --- | --- |
| Patched dependency audit | 76 inventory entries; zero known vulnerabilities in audited dependencies; no vulnerability IDs ignored | The local Mnemion 4.43.0 package is unavailable on PyPI and was skipped by the auditor. This is dependency-audit evidence, not a full product security assessment. |
| Binary dependency preflight | All five service wheel targets passed, covering the six desktop targets | Locked wheel resolution with Python 3.13.16; native execution and packaging remain separate gates. |
| Pinned multilingual E5 small | Query and document vectors, each 384-dimensional, were bit-identical before/after; maximum absolute difference 0 | Same generation, 23 tokens and complete `[0, 87)` character span for one synthetic fixture. |
| Pinned BGE small English v1.5 | Query and document vectors, each 384-dimensional, were bit-identical before/after; maximum absolute difference 0 | Same generation, 26 tokens and complete `[0, 87)` character span for the same synthetic fixture. |

The real-model comparison passed at **01:43:02 UTC**. Network access was
explicitly blocked in both comparison processes. The missing pinned E5 files
were downloaded and verified separately before comparison; earlier missing-cache
attempts failed before inference and remain preserved. No cloud model calls or
production requests were made during the comparison.

Retained evidence: `dependency-audit.log`, `PYSEC-2026-4320.json`,
`pillow-12.3.0-advisories.json`, `security-audit.json`, `security-audit.log`,
`security-binary-preflight-r2.log`, `security-model-parity.json` and the separate
baseline/patched comparison artifacts. These results establish bounded parity
for the tested text workload. Native packaging, public update gates and actual
installed acceptance remain required. The unfinished L1 work and all broader
requirement statuses remain separate and unchanged.
