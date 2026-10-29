# Qualification probes on the v3 contract — 29 October 2026

The actual-app probe listeners now use `CollectorV3` and `POST /v3/report`.
`wire-v3.json` fixes the packet at 25 bytes. Manual review retains a body only
when that body is exactly one 25-byte synthetic packet. A shorter prefix, a
longer body, or any non-review run keeps no body. Preference setup uses
`policy.DISCLOSURE_VERSION` from the release disclosure. That value is 1 in
the current disclosure file; the probes no longer type the old approval number
themselves.

New diagnostic receipts record `wire_version` 3, `/v3/report`, and
`packet_bytes` 25, and every case in that receipt must record the same three
fields. A case with no wire metadata, or with a conflicting 4-byte `/v1/report`
label, is rejected rather than called v3. A receipt that itself has none of
those fields stays `historical-v2`. Partial explicit metadata is rejected
instead of being filled in. Review capture counts every received byte, then
drops the retained body once the total passes 25 bytes or eight chunks. It
does not keep an accepted prefix. Collector refusal is unchanged.
`resource_acceptance` stays false. The optional nine-phase counters and the
ordinary-mode `None` result are unchanged.

The pinned Linux interpreter ran:

`/home/jorqu/.local/state/mnemion-release/2026-10-10/release-venv/bin/python -m pytest tests/test_telemetry_renderer_report.py -q --tb=short -k "reviewed_v3 or v3_diagnostic or counterbalanced or phase_memory"`

7 passed, 40 deselected, in 14.67s. Ruff 0.15.11 format and check reported no
changes on the touched Python files. No JavaScript file was edited. No app
trial was run.

This does not qualify the client integration that is still being wired. No app,
browser, or installed run was executed for this note. Production collection,
destination, and route stay false/null/null. V08 remains Building. The 2 MiB
and 0.5 percent gates, and every earlier resource failure, stay failed.
