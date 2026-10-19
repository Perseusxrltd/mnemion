# Legacy buffer reconciliation — 19 October 2026

Source 4.25 adds a [reviewed import](../service/legacy-buffer.md) for the older
external JSONL prototype in issue 39. The prototype format was inspected from
the preserved original; its private code was neither executed nor copied into
the public implementation. Its newer encrypted publication and older receipt
race remain explicit adoption boundaries.

## Verified source behavior

The focused run passed **45 cases**: 22 importer cases and 23 existing agent/API/
SDK compatibility cases. Tests use real disposable PostgreSQL with separate
non-owner service and worker logins. They cover:

- Preview without writes, stable native identities and duplicate-line folding.
- Exact Unicode content and original writer/kind/time provenance; no inherited
  principal or grant.
- Repeat imports and matching idempotency receipts, preservation of native edits,
  and whole-batch refusal when a source ID changes.
- Explicit withdrawals for present and absent records, immediate denial, purge
  and refusal to resurrect older copies. Ordinary native deletion is retained.
- Current organization/space authority, private-destination enforcement and
  rejection of an already enrolled Git publication policy.
- Invalid/partial records, duplicate JSON keys, conflicting IDs, record limits,
  unknown fields, naive timestamps, Windows CRLF/BOM and Unicode line separators.
- Mandatory secret checks, explicit personal-data policy, and omission of
  rejected secret-like writer labels from the preview.
- Real HTTP preview/import/keyword recall; Python SDK private-input serialization
  and repeatability; private agent catalog metadata. Existing MCP and client
  compatibility cases still pass.

```sh
python -m pytest service_tests/test_buffer_import.py \
  service_tests/test_agent_control.py service_tests/test_clients.py -q
```

The 25 PostgreSQL migration/installed-inventory checks also passed. Their local
receipt fingerprint is
`2fb1911656ed8811785afc067b4d826ce167294e9376f19d8c3e997a4521333b`.
There is no new migration or dependency in this batch. Existing table lifecycles
retain aliases and negative recovery identities; a new full disaster-recovery
drill is not claimed by these tests.

## Actual app flow

A Chromium browser connected through the ordinary workspace-key screen to a
separate local HTTP server and real PostgreSQL database. All records and the
workspace were invented for this check. Through the actual file picker and
review controls:

1. Three complete lines produced two distinct records and one identical duplicate.
2. One supplied withdrawal left one new positive memory and one retained denial.
3. Explicit review/import completed, and **Open memory** showed the exact Unicode
   content, normal revision controls and original source evidence.
4. After reloading the rebuilt app and reconnecting, the same files reviewed as
   **already imported** and **already withdrawn**. No new identity was proposed.

The visual pass caught and corrected an HTML pattern incompatibility and missing
field styling. The final review rendered with the existing Perseus colors,
field components and spacing, and no browser console errors or warnings.
Selected source text is kept in page memory rather than browser storage.

The deterministic fixture embedder validates transactions and integration only;
it is not a semantic-quality baseline. Desktop native packaging and installed
automatic updates remain the separate release gates. No original office data,
encrypted repository contents, live host, production credential or Argil runtime
was changed by this check. Issue 39 remains open for its broader reconstruction
and deployment acceptance work.
