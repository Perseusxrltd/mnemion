import { useState } from 'react'
import type { TelemetryWorkflowCoverage } from '../../../shared/product-telemetry'

/** Fixed product metadata only; neither the filters nor rows inspect activity. */
export default function TelemetryCoverage({ coverage }: { coverage: TelemetryWorkflowCoverage }) {
  const [family, setFamily] = useState('all')
  const [state, setState] = useState('all')
  const families = [...new Set(coverage.workflows.map(row => row.workflow.split('.')[0]))]
  const rows = coverage.workflows.filter(row =>
    (family === 'all' || row.workflow.startsWith(family + '.')) && (state === 'all' || row.state === state))
  return <>
    <p><strong>{coverage.summary.mapped} of {coverage.summary.total}</strong> categories have mapped measurement sources.
      {' '}<strong>{coverage.summary.unmeasured}</strong> have no mapped source and remain unmeasured.</p>
    <p>A mapped category is not measured on every screen or client. Your privacy choice and the collection status above still apply.</p>
    <div className="ws-form-row">
      <label className="ws-field"><span>Feature family</span><select value={family} onChange={event => setFamily(event.target.value)}>
        <option value="all">All features</option>{families.map(name => <option key={name} value={name}>{name}</option>)}
      </select></label>
      <label className="ws-field"><span>Measurement coverage</span><select value={state} onChange={event => setState(event.target.value)}>
        <option value="all">All categories</option><option value="mapped">Mapped source</option><option value="unmeasured">Unmeasured</option>
      </select></label>
    </div>
    <p role="status">{rows.length} categories shown.</p>
    <div className="ws-table-wrap"><table className="ws-table">
      <caption>Telemetry category coverage in this version</caption>
      <thead><tr><th scope="col">Category</th><th scope="col">Coverage</th><th scope="col">Measurement source</th></tr></thead>
      <tbody>{rows.map(row => <tr key={row.workflow}>
        <th scope="row">{row.workflow.replaceAll('_', ' ')}</th>
        <td>{row.state === 'mapped' ? 'Mapped source' : 'Unmeasured'}</td>
        <td>{row.owners.length ? row.owners.map(owner => coverage.owners[owner]).join(', ') : 'No current source mapping'}</td>
      </tr>)}</tbody>
    </table></div>
    {!rows.length && <p>No categories match these filters.</p>}
  </>
}
