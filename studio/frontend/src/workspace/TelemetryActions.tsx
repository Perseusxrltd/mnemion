import { useState } from 'react'
import type { TelemetryActionCoverage } from '../../../shared/product-telemetry'

const labels = { mapped: 'Declared source', excluded: 'Excluded', delegated: 'Owned elsewhere', unmeasured: 'Unmeasured' }
const PAGE_SIZE = 50

/** This metadata view never invokes the actions it describes. */
export default function TelemetryActions({ coverage, owners }: { coverage: TelemetryActionCoverage; owners: Record<string, string> }) {
  const [query, setQuery] = useState('')
  const [owner, setOwner] = useState('all')
  const [state, setState] = useState('all')
  const [page, setPage] = useState(0)
  const needle = query.trim().toLowerCase()
  const rows = coverage.actions.filter(row => (owner === 'all' || row.owner === owner) &&
    (state === 'all' || row.state === state) && (!needle ||
      [row.action, row.variant ?? '', owners[row.owner], ...row.workflows].join(' ').toLowerCase().includes(needle)))
  const current = Math.min(page, Math.max(0, Math.ceil(rows.length / PAGE_SIZE) - 1))
  const visible = rows.slice(current * PAGE_SIZE, (current + 1) * PAGE_SIZE)
  return <>
    <p><strong>{coverage.summary.total}</strong> actions and fixed variants: {coverage.summary.mapped} with declared sources,
      {' '}{coverage.summary.excluded} excluded, {coverage.summary.delegated} owned elsewhere and {coverage.summary.unmeasured} unmeasured.</p>
    <p>This is a source inventory, not your activity history. A declared source still requires your privacy permission;
      it does not prove coverage on every screen, sensor or installed client.</p>
    <div className="ws-form-row">
      <label className="ws-field"><span>Find an action</span><input value={query} type="search"
        onChange={event => { setQuery(event.target.value); setPage(0) }} /></label>
      <label className="ws-field"><span>Action source</span><select value={owner}
        onChange={event => { setOwner(event.target.value); setPage(0) }}>
        <option value="all">All sources</option>{Object.entries(owners).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
      </select></label>
      <label className="ws-field"><span>Action coverage</span><select value={state}
        onChange={event => { setState(event.target.value); setPage(0) }}>
        <option value="all">All actions</option>{Object.entries(labels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
      </select></label>
    </div>
    <p role="status">{rows.length} actions and variants match{rows.length ? `; showing ${current * PAGE_SIZE + 1}–${current * PAGE_SIZE + visible.length}` : ''}.</p>
    <div className="ws-table-wrap"><table className="ws-table">
      <caption>Individual telemetry action coverage in this version</caption>
      <thead><tr><th scope="col">Action</th><th scope="col">Source</th><th scope="col">Coverage</th><th scope="col">Mapping or reason</th></tr></thead>
      <tbody>{visible.map(row => <tr key={`${row.owner}:${row.action}:${row.variant ?? ''}`}>
        <th scope="row">{row.action}{row.selector && <small><br />{row.selector} = {row.variant}</small>}</th>
        <td>{owners[row.owner]}</td><td>{labels[row.state]}</td>
        <td>{row.workflows.length ? row.workflows.join(', ') : row.reason ? coverage.reasons[row.reason] : row.delegate ?
          <button className="ws-button" onClick={() => { setOwner(row.delegate!); setState('all'); setQuery(''); setPage(0) }}>Inspect {owners[row.delegate]}</button> :
          'No reviewed source mapping'}</td>
      </tr>)}</tbody>
    </table></div>
    {!rows.length && <p>No actions match these filters.</p>}
    {rows.length > PAGE_SIZE && <div className="ws-form-row">
      <button className="ws-button" disabled={current === 0} onClick={() => setPage(current - 1)}>Previous actions</button>
      <button className="ws-button" disabled={(current + 1) * PAGE_SIZE >= rows.length} onClick={() => setPage(current + 1)}>Next actions</button>
    </div>}
  </>
}
