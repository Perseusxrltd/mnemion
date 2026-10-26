# Telemetry: visible source coverage

**26 October 2026, source implementation.** The app/browser privacy page and
offline native `schema`/`preview` controls now distinguish mapped telemetry
categories from unmeasured categories. This closes the misleading display that
listed the entire catalog as though every category had a measurement source.
It does not complete workflow, sensor, anonymity or release qualification.
V08 remains Building; collection is false and destination/route remain null.

## Shared, generated inventory

[`deploy.telemetry_coverage`](../../deploy/telemetry_coverage.py) derives the
[inventory](../../mnemion/product_telemetry/workflow-coverage.json) from the
catalog and six reviewed origin maps. Each of the **94 categories** occurs once,
with declared source owners or an explicit `unmeasured` state. Variant selectors
and Studio/local-stdio delegation resolve through the same control map; excluded
paths acquire no owner. Unknown workflow references fail generation.

There are currently **86 mapped categories and eight unmeasured categories**:
`backup.list`, `capture.deliver`, `capture.pause`, `capture.preview`,
`models.prepare`, `update.rollback`, `update.verify` and `workspace.switch`.
These are counts of catalog entries with source references, not coverage
percentages for screens, sensors, users or the full roadmap. Substeps may belong
to an enclosing workflow; an unmeasured row does not imply an application
feature is absent. The inventory makes no new measurement owner or collection
permission. Existing operation-level exclusions remain in the full schema.

The generated JSON is **16,260 bytes** and contains only fixed public product
metadata and hashes of its seven source inputs. It reads no settings, account,
workspace, usage or operational history. Native discovery loads it only on
explicit schema/format inspection. The browser loads it as a separate asset
only when the user requests the format preview, then reads current privacy
state. Ordinary startup, status and producers do not import this inventory.

Release preparation regenerates the file; the existing release validator
rejects stale contents. Editing or adding a mapped workflow cannot silently
leave the privacy page's earlier claim in place. The generated file is committed
alongside its source maps and included by the existing Python package-data
collection. No extra telemetry service or runtime dependency was introduced.

## User and agent controls

Expand **Workflow coverage and exclusions** after **Show report format** in
Privacy. The table supports feature-family and mapped/unmeasured filters,
labelled form controls, a caption, row/column headers and an empty-result state.
It retains the explicit collection status and privacy exclusions. Older native
engines without the inventory show an honest unavailable-coverage message.

Existing offline `schema` and `preview` responses expose `workflow_coverage`
with the same schema version, summary, rows and qualification. Reading it does
not acknowledge disclosure, create private state, reserve a report, spend an
allowance or send telemetry. The preview remains synthetic; no actual outbound
packet is implied. UI choice/status/focus invalidation still rejects late
preview replies.

## Verification and limits

The focused source selection passed **19 Python checks and 25 browser-source
checks**, with no skips. It exercises new/disabled/restricted/damaged/in-flight
and cooldown preview states, unchanged private files, native schema/preview
equality, lazy browser loading, removed owners, new unmeasured workflows and
stale release rejection. Python/TypeScript catalog-coordinate checks remain
included. The frontend type check and production build passed.

The actual Chrome journey against the compiled 4.46.18 browser bundle confirmed
all 94 rows, eight unmeasured rows, the two unmeasured update categories and an
empty filtered result. A 390-pixel viewport had no page overflow. The inventory
asset was absent before inspection and loaded once afterward; filtering left
privacy storage empty. Opt-out cleared the displayed preview and showed the
disabled state. The observed resources all used the isolated loopback origin,
with zero report requests, console warnings or console errors. The browser and
preview server closed, and their process/listener absence was verified.

The final frontend and Electron builds passed, and **29 release-automation
checks** passed. The documentation review confirmed that the formal V08
contract, all 66 requirement rows and all 43 prior resolved evidence links are
preserved. Its first checker compared raw links across different directories;
that false failure is retained, and the corrected check resolves paths and
anchors without changing the documentation to satisfy it.

Private input hashes, command receipts and browser observations are retained in
`/home/jorqu/mnemion-completion/2026-10-26-telemetry-coverage/`.
`documentation-and-browser-inputs.json` identifies the 519 compiled browser
files used by the journey. `browser-acceptance.json` and `browser-commands.json`
retain the actual observations and commands; `builds.json`,
`release-automation-checks.log` and `source-checks.json` describe their respective
validation scopes. Later documentation edits do not reclassify that original
browser bundle as an installed release.

These checks concern disclosure accuracy and read-only controls. They do not
qualify active ingestion, installed native targets, provider retention or the
unchanged 2 MiB / 0.5% resource limits. The separate
[pinned SQLite decision](2026-10-26-telemetry-private-sqlite.md) preserves its
original failures and all completed measurements without selecting a replacement
backend. Current release availability is maintained in [release status](../RELEASE_STATUS.md).
