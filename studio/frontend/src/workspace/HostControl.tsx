import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, Copy, KeyRound, LoaderCircle, RefreshCw, Server, ShieldCheck } from 'lucide-react'
import type { HostConnection, HostInspection, HostProfilesStatus, HostRequest } from '../../../shared/host-control'
import './workspace.css'
import './host-control.css'

const message = (error: unknown) => error instanceof Error ? error.message : 'This operation could not be confirmed.'
const when = (value: string | null | undefined) => value ? new Date(value).toLocaleString() : 'Not recorded'
const labels: Record<string, string> = {
  'service.start': 'Start memory service', 'service.stop': 'Stop memory service',
  'upgrade.plan': 'Review update', 'upgrade.apply': 'Apply reviewed update',
  'operators.grant': 'Grant host access', 'operators.revoke': 'Revoke host access',
  'operations.resolve': 'Accept inspected recovery state',
}
const phases: Record<string, string> = { submitted: 'Awaiting acknowledgement', queued: 'Queued', running: 'Running',
  inspection_required: 'Needs inspection', succeeded: 'Completed', failed: 'Failed', cancelled: 'Cancelled', refused: 'Refused' }
const reads = new Set(['host.status', 'operations.get', 'operations.list', 'operators.list'])

export default function HostControl() {
  const api = window.mnemion?.hostControl
  const [profiles, setProfiles] = useState<HostProfilesStatus>({ profiles: [], secure_storage: false })
  const [selected, setSelected] = useState('')
  const [name, setName] = useState('')
  const [inspection, setInspection] = useState<HostInspection | null>(null)
  const [receipt, setReceipt] = useState<Record<string, any> | null>(null)
  const [people, setPeople] = useState<Record<string, any> | null>(null)
  const [history, setHistory] = useState<Record<string, any> | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState('')
  const working = useRef(false)
  const generation = useRef(0)
  const historyPage = useRef(0)
  const focusedOperation = useRef('')
  const [connectionText, setConnectionText] = useState('')
  const [confirmIdentity, setConfirmIdentity] = useState(false)
  const [interruption, setInterruption] = useState(false)
  const [plan, setPlan] = useState<Record<string, any> | null>(null)
  const reviewedPlan = useRef('')
  const [approval, setApproval] = useState(false)
  const [publicRole, setPublicRole] = useState('operator')
  const [grantText, setGrantText] = useState('')
  const [grantRole, setGrantRole] = useState('observer')
  const [grantExpiry, setGrantExpiry] = useState('')
  const [confirmGrant, setConfirmGrant] = useState(false)
  const [issuedConnection, setIssuedConnection] = useState<HostConnection | null>(null)
  const [revoke, setRevoke] = useState<Record<string, any> | null>(null)
  const [confirmRecovery, setConfirmRecovery] = useState(false)
  const [settle, setSettle] = useState<'observe' | 'stop'>('observe')
  const [forget, setForget] = useState(false)
  const [acknowledgeOutstanding, setAcknowledgeOutstanding] = useState(false)
  const [archiveOutstanding, setArchiveOutstanding] = useState(false)
  const [recoveries, setRecoveries] = useState<Record<string, any>[]>([])
  const profile = profiles.profiles.find(item => item.id === selected)
  const authority = inspection?.status.ok ? inspection.status.result : null
  const service = authority?.service
  const actions: string[] = authority?.actions ?? []

  function showPlan(value: Record<string, any> | null) {
    const identity = value ? `${value.plan_id}:${value.plan_sha256}` : ''
    if (identity !== reviewedPlan.current) setApproval(false)
    reviewedPlan.current = identity
    setPlan(value)
  }

  async function loadProfiles() {
    if (!api) return
    const [value, savedRecovery] = await Promise.all([api('host.profiles'), api('host.recoveries')])
    setProfiles(value)
    setRecoveries(savedRecovery.records)
    setSelected(current => value.profiles.some(item => item.id === current) ? current : value.profiles[0]?.id ?? '')
  }
  async function run(label: string, action: () => Promise<void>) {
    if (working.current) return
    working.current = true; setBusy(label); setError(''); setNotice('')
    try { await action() } catch (error) { setError(message(error)) }
    finally { working.current = false; setBusy('') }
  }
  async function refresh(id: string, expectedGeneration = generation.current) {
    if (!api) return
    const observed = await api('host.inspect', { id })
    if (expectedGeneration !== generation.current) return
    setInspection(observed)
    if (historyPage.current === 0) setHistory(observed.history?.ok ? observed.history.result : null)
    if (observed.operation?.ok && (!focusedOperation.current || focusedOperation.current === observed.operation.result?.operation_id)) {
      setReceipt(observed.operation.result)
      if (observed.operation.result?.action === 'upgrade.plan' && observed.operation.result.phase === 'succeeded') showPlan(observed.operation.result.result)
    }
    await loadProfiles()
    if (!observed.status.ok) throw new Error(observed.status.error?.message ?? 'The host did not accept this login.')
  }
  useEffect(() => { void run('Reading saved host logins…', loadProfiles) }, [])
  useEffect(() => {
    const current = ++generation.current
    historyPage.current = 0; focusedOperation.current = ''
    setInspection(null); setPeople(null); setPlan(null); setReceipt(null); setHistory(null)
    setConnectionText(''); setConfirmIdentity(false); setIssuedConnection(null); setForget(false); setAcknowledgeOutstanding(false)
    setInterruption(false); setApproval(false); setConfirmRecovery(false); setRevoke(null); setArchiveOutstanding(false)
    if (!selected || !profiles.profiles.find(item => item.id === selected)?.connection) return
    const poll = () => {
      if (!working.current && document.visibilityState !== 'hidden') void run('Checking independent host connection…', () => refresh(selected, current))
    }
    // Let the enrollment/profile action release its busy state first.
    const initial = setTimeout(poll, 0)
    const timer = setInterval(poll, 15000)
    return () => { clearTimeout(initial); clearInterval(timer); generation.current++ }
  }, [selected, !!profile?.connection])

  function request(action: string, fields: Record<string, unknown> = {}): HostRequest {
    if (!profile?.connection) throw new Error('Enroll this host login first.')
    const now = Date.now()
    return { protocol: 1, host_id: profile.connection.host_id, request_id: crypto.randomUUID(), action,
      ...(!reads.has(action) ? { issued_at: new Date(now).toISOString(), valid_until: new Date(now + 3600000).toISOString() } : {}), ...fields }
  }
  async function send(action: string, fields: Record<string, unknown> = {}) {
    if (!api || !profile) throw new Error('Choose a host login.')
    if (!reads.has(action)) focusedOperation.current = ''
    const reply = await api('host.request', { id: profile.id, request: request(action, fields) })
    await loadProfiles()
    if (!reply.ok) throw new Error(reply.error?.message ?? 'The host refused this operation.')
    return reply.result!
  }
  async function inspectOperation(id: string) {
    const result = await send('operations.get', { operation_id: id })
    focusedOperation.current = id
    setReceipt(result); setConfirmRecovery(false)
    if (result.action === 'upgrade.plan' && result.phase === 'succeeded') { showPlan(result.result); setApproval(false) }
  }
  async function copy(text: string) {
    await navigator.clipboard.writeText(text)
    setNotice('Copied. This document contains public enrollment information only.')
  }
  const publicEnrollment = profile ? JSON.stringify({ name: profile.name, public_key: profile.public_key, role: publicRole, expires_at: null }, null, 2) : ''

  return <main className="workspace ws-host-page">
    <header className="ws-host-header"><div><p className="ws-eyebrow">Organization infrastructure</p><h1><Server aria-hidden="true" size={28} /> Host controls</h1><p>Manage a company memory host independently of its memory service.</p></div><Link className="ws-button" to="/workspace"><ArrowLeft size={16} />Back to workspace</Link></header>
    {!api ? <section className="ws-card"><h2>Use the desktop app for host administration</h2><p>Your browser cannot open this protected host connection. Open Mnemion Studio on Windows, Mac or Linux, then choose Host controls.</p><a className="ws-button ws-primary" href="https://github.com/Perseusxrltd/mnemion/releases/latest" target="_blank" rel="noreferrer">Get Mnemion Studio</a></section> : <>
      {!!error && <div className="ws-notice ws-error" role="alert">{error}</div>}
      {!!notice && <p className="ws-notice" role="status">{notice}</p>}
      {!!busy && <p className="ws-host-progress" role="status"><LoaderCircle size={16} className="ws-spin" />{busy}</p>}
      <div className="ws-host-columns"><aside className="ws-host-list">
        <section className="ws-card"><h2>Host logins on this device</h2><p className="ws-helper">Each device or agent has its own key and explicit host role.</p>
          <label className="ws-field">Saved login<select data-update-safe value={selected} disabled={!!busy} onChange={event => setSelected(event.target.value)}><option value="">Choose a login</option>{profiles.profiles.map(item => <option key={item.id} value={item.id}>{item.name}{item.connection ? ` · ${item.connection.hostname}` : ' · awaiting enrollment'}</option>)}</select></label>
          <form onSubmit={event => { event.preventDefault(); void run('Creating a protected host login…', async () => {
            const created = await api('host.create', { name }); await loadProfiles(); setSelected(created.id); setName('')
          }) }}><label className="ws-field">New device or agent name<input value={name} maxLength={80} required placeholder="Alice’s work laptop" onChange={event => setName(event.target.value)} /></label><button className="ws-button" disabled={!!busy || !profiles.secure_storage || !name.trim()}><KeyRound size={16} />Create host login</button></form>
          {!profiles.secure_storage && <p className="ws-notice">Unlock the operating system’s secure store to create or use a host login.</p>}
        </section>
        <section className="ws-card"><h2>When can this help?</h2><p>Start or repair an adopted host when the memory service is stopped, a migration is interrupted, or the original agent is unavailable.</p><p className="ws-helper">The computer and its independent controller must be running and reachable. If the computer itself is off, use your hosting provider or company’s infrastructure controls.</p><Link className="ws-link" to="/help?doc=docs%2Fguides%2Fcompany-host-control.md">Setup, recovery and agent guide</Link></section>
        {!!recoveries.length && <section className="ws-card"><h2>Retained recovery requests</h2><p className="ws-helper">Public records of unfinished work from a previous login or recovery attempt. A current host custodian can inspect the original operation.</p>{recoveries.map(record => <details key={record.id}><summary>{record.name} · {labels[record.action] ?? record.action}</summary><p>{record.hostname}</p><code>{record.operation_id}</code><p className="ws-helper">Recorded {when(record.recorded_at)}. Original outcome remains unconfirmed.</p><button className="ws-button" disabled={!!busy} onClick={() => void run('Copying public recovery information…', async () => copy(JSON.stringify(await api('host.recovery', { id: record.id }), null, 2)))}>Copy recovery document</button></details>)}</section>}
      </aside><div className="ws-host-content">
        {!profile && <section className="ws-card"><ShieldCheck size={30} /><h2>A host login that outlives an agent session</h2><p>Create a protected login, then give its public enrollment document to the host owner. They choose your permissions and return the host connection.</p><p>Memory accounts and vault permissions remain separate from host administration.</p></section>}
        {profile && <>
          <section className="ws-card"><div className="ws-section-title"><h2>{profile.name}</h2>{profile.connection && <button className="ws-button" disabled={!!busy} onClick={() => void run('Refreshing host status…', () => refresh(profile.id))}><RefreshCw size={15} />Refresh</button>}</div>
            {profile.connection ? <><p className="ws-host-address">{profile.connection.hostname}:{profile.connection.port}</p><dl className="ws-host-facts"><div><dt>Your current role</dt><dd>{authority?.operator?.role ?? 'Not verified'}</dd></div><div><dt>Memory service</dt><dd>{service?.ready ? 'Ready' : service?.running ? 'Running · needs attention' : service?.running === false ? 'Stopped' : 'Not verified'}</dd></div><div><dt>Installed version</dt><dd>{service?.version ?? 'Unknown'}</dd></div><div><dt>Last observation</dt><dd>{when(authority?.observed_at)}</dd></div></dl>
              {service?.recovery_required && <p className="ws-notice">An interrupted update needs recovery. Review an update plan to continue its recorded steps.</p>}
              {service?.service_policy?.desired === 'stopped' && <p className="ws-helper">An administrator has kept this memory service stopped. Its configured startup manager must preserve this decision until an approved start or update.</p>}
              {service?.service_policy?.desired === 'stopped' && service?.running && !service?.service_policy?.pending_work && <p className="ws-notice">The service is running despite its saved stop decision. Ask the host owner to check its startup and automatic repair settings.</p>}
              {service?.service_policy?.start_needs_inspection && <p className="ws-notice">An automatic start could not be confirmed. Inspect the host, then explicitly approve a new start if needed; Mnemion will not repeat the uncertain request.</p>}
              {(service?.controller?.fallback || service?.controller?.update_needs_inspection) && <p className="ws-notice">The independent controller kept its last working runtime. Its update needs inspection.</p>}
              <details><summary>Verified connection details</summary><p className="ws-helper">Host identity: {profile.connection.host_id}</p><p className="ws-helper">Operator identity: {profile.connection.operator_id}</p><p className="ws-helper">Pinned server key: <code>{profile.connection.host_key_fingerprint}</code></p><p className="ws-helper">Device key: <code>{profile.fingerprint}</code></p></details>
            </> : <><p>Share this public document with a current host custodian. For a new host, its operating-system owner uses it during adoption.</p><label className="ws-field">Requested role<select value={publicRole} onChange={event => setPublicRole(event.target.value)}><option value="observer">Observer · inspect only</option><option value="operator">Operator · service and updates</option><option value="custodian">Custodian · also manage host access</option></select></label><pre className="ws-code">{publicEnrollment}</pre><button className="ws-button" onClick={() => void run('Copying public enrollment…', () => copy(publicEnrollment))}><Copy size={15} />Copy public enrollment</button>
              <form onSubmit={event => { event.preventDefault(); void run('Saving the verified host enrollment…', async () => {
                const value = JSON.parse(connectionText)
                await api('host.enroll', { id: profile.id, connection: value.connection ?? value, confirm: confirmIdentity }); await loadProfiles(); setConnectionText(''); setConfirmIdentity(false)
              }) }}><label className="ws-field">Host connection from your custodian<textarea rows={7} value={connectionText} maxLength={8192} required spellCheck={false} onChange={event => { setConnectionText(event.target.value); setConfirmIdentity(false) }} placeholder="Paste the public host connection JSON" /></label><label className="ws-checkbox"><input type="checkbox" checked={confirmIdentity} onChange={event => setConfirmIdentity(event.target.checked)} />I verified this host and server fingerprint with its owner.</label><button className="ws-button ws-primary" disabled={!!busy || !confirmIdentity || !connectionText.trim()}>Save host connection</button></form>
            </>}
          </section>
          {profile.connection && <>
            {actions.includes('service.start') && <section className="ws-card"><h2>Memory service</h2><p>These controls manage the memory service while the independent host connection remains available.</p><label className="ws-checkbox"><input type="checkbox" checked={interruption} onChange={event => setInterruption(event.target.checked)} />I approve service changes and possible interruption for this host.</label><div className="ws-actions">{(['service.start', 'service.stop'] as const).map(action => <button key={action} className="ws-button" disabled={!!busy || !interruption || service?.recovery_required} onClick={() => void run(labels[action] + '…', async () => { await send(action, { approve_service_interruption: interruption }); setInterruption(false); await refresh(profile.id) })}>{labels[action]}</button>)}</div></section>}
            {actions.includes('upgrade.plan') && <section className="ws-card"><div className="ws-section-title"><h2>Updates & recovery</h2><button className="ws-button" disabled={!!busy} onClick={() => void run('Requesting a current update plan…', async () => { setPlan(null); setApproval(false); await send('upgrade.plan'); await refresh(profile.id) })}>Review available update</button></div><p>Before changing this host, Mnemion verifies the signed release and a fresh encrypted backup downloaded from its configured independent Git destination.</p><dl className="ws-host-facts"><div><dt>Independent backup</dt><dd>{service?.backups?.configured ? 'Configured' : 'Owner setup required'}</dd></div><div><dt>Controller</dt><dd>{service?.controller?.version ?? 'Unknown'}</dd></div></dl>
              {plan && <div className="ws-host-plan"><h3>{plan.resume ? 'Resume recorded update' : plan.target_version ? `Update to ${plan.target_version}` : 'Update check'}</h3>{plan.target_version ? <><p>From {plan.current_version ?? service?.version} to {plan.target_version}. Service interruption is required.</p><p className="ws-helper">Source: <code>{plan.source_commit}</code><br />Plan valid until {when(plan.valid_until)}.</p><p className="ws-helper">Database changes use forward recovery. A failure does not automatically restore an older database.</p>{!plan.independent_backup_configured && <p className="ws-notice">Ask the host owner to configure independent encrypted backups and recovery-key custody before applying this plan.</p>}<label className="ws-checkbox"><input type="checkbox" checked={approval} onChange={event => setApproval(event.target.checked)} />I reviewed this version and approve its service interruption.</label><button className="ws-button ws-primary" disabled={!!busy || !approval || !plan.independent_backup_configured || Date.parse(plan.valid_until) <= Date.now()} onClick={() => void run('Submitting the reviewed update…', async () => {
                  await send('upgrade.apply', { plan_id: plan.plan_id, plan_sha256: plan.plan_sha256, approve_service_interruption: approval }); setApproval(false); setPlan(null); await refresh(profile.id)
                })}>{plan.resume ? 'Resume this update' : 'Apply this update'}</button></> : <p>{plan.status === 'up_to_date' ? 'This host is up to date.' : `Update status: ${plan.status}`}</p>}</div>}
            </section>}
            <section className="ws-card"><div className="ws-section-title"><h2>Operation history</h2><button className="ws-button" disabled={!!busy} onClick={() => void run('Loading recent host operations…', async () => { const latest = await send('operations.list', { limit: 25 }); historyPage.current = 0; setHistory(latest) })}>Latest</button></div>
              {profile.last_operation && <div className="ws-notice"><p>Last request from this device: {labels[profile.last_operation.request.action] ?? profile.last_operation.request.action} · {phases[profile.last_operation.phase] ?? profile.last_operation.phase}</p><code>{profile.last_operation.request.request_id}</code><div className="ws-actions"><button className="ws-button" disabled={!!busy} onClick={() => void run('Inspecting the saved operation…', () => inspectOperation(profile.last_operation!.request.request_id))}>Inspect saved request</button>{profile.last_operation.phase === 'submitted' && <button className="ws-button" disabled={!!busy || Date.parse(profile.last_operation.request.valid_until ?? '') <= Date.now()} onClick={() => void run('Reconciling the exact saved request…', async () => {
                  const response = await api('host.request', { id: profile.id, request: profile.last_operation!.request }); await loadProfiles(); if (!response.ok) throw new Error(response.error?.message); await refresh(profile.id)
                })}>Retry the same request</button>}</div>{['submitted', 'inspection_required'].includes(profile.last_operation.phase) && <details><summary>Keep this recovery record and clear the local pending request</summary><p>The request remains available to inspect through another custodian. This does not stop or cancel remote work.</p><label className="ws-checkbox"><input type="checkbox" checked={archiveOutstanding} onChange={event => setArchiveOutstanding(event.target.checked)} />Keep the original public request; I understand the remote operation may still be active.</label><button className="ws-button" disabled={!!busy || !archiveOutstanding} onClick={() => void run('Preserving the original recovery request…', async () => { await api('host.request.archive', { id: profile.id, confirm: archiveOutstanding }); setArchiveOutstanding(false); await loadProfiles() })}>Keep recovery record</button></details>}</div>}
              {!history?.operations?.length && <p className="ws-helper">No operation history is available yet. Refresh after connecting.</p>}
              {!!history?.operations?.length && <div className="ws-table-wrap"><table className="ws-table"><thead><tr><th>Operation</th><th>State</th><th>Updated</th><th>Details</th></tr></thead><tbody>{history.operations.map((item: Record<string, any>) => <tr key={item.operation_id}><td>{labels[item.action] ?? item.action}</td><td>{phases[item.phase] ?? item.phase}</td><td>{when(item.updated_at)}</td><td><button className="ws-link" disabled={!!busy} onClick={() => void run('Reading host operation…', () => inspectOperation(item.operation_id))}>Inspect</button></td></tr>)}</tbody></table></div>}
              {history?.next_offset != null && <button className="ws-button" disabled={!!busy} onClick={() => void run('Loading older host operations…', async () => { const offset = history.next_offset; const older = await send('operations.list', { limit: 25, offset }); historyPage.current = offset; setHistory(older) })}>Older operations</button>}
              {receipt && <div className="ws-host-receipt"><h3>{labels[receipt.action] ?? receipt.action}</h3><p>{phases[receipt.phase] ?? receipt.phase} · {when(receipt.updated_at)}</p><code>{receipt.operation_id}</code>{receipt.error && <p className="ws-notice">Recorded failure: {receipt.error === 'host_busy' ? 'The host is finishing another operation or source scan. Refresh its status and inspect this request before requesting new work.' : receipt.error}</p>}{receipt.result && <details><summary>Recorded result</summary><pre className="ws-code">{JSON.stringify(receipt.result, null, 2)}</pre></details>}
                {receipt.phase === 'inspection_required' && actions.includes('operations.resolve') && <><p>Accept a stable current state after inspecting this host. The original operation remains recorded as unconfirmed; accepting recovery does not mark it successful.</p><label className="ws-field">Recovery action<select value={settle} onChange={event => { setSettle(event.target.value as typeof settle); setConfirmRecovery(false) }}><option value="observe">Accept the stable current state</option><option value="stop">Stop memory service, then accept its stopped state</option></select></label><label className="ws-checkbox"><input type="checkbox" checked={confirmRecovery} onChange={event => setConfirmRecovery(event.target.checked)} />I inspected this host and approve this recovery{settle === 'stop' ? ' and service interruption' : ''}.</label><button className="ws-button" disabled={!!busy || !confirmRecovery || service?.recovery_required} onClick={() => void run('Recording the inspected recovery…', async () => { await send('operations.resolve', { operation_id: receipt.operation_id, approve_current_state: confirmRecovery, settle, approve_service_interruption: settle === 'stop' && confirmRecovery }); setConfirmRecovery(false); await refresh(profile.id) })}>Accept inspected state</button></>}
              </div>}
            </section>
            {actions.includes('operators.list') && <section className="ws-card"><div className="ws-section-title"><h2>Host access</h2><button className="ws-button" disabled={!!busy} onClick={() => void run('Reading current host access…', async () => setPeople(await send('operators.list', { limit: 50 })))}>Refresh people & agents</button></div><p>Observers inspect. Operators manage service and updates. Custodians also grant, revoke and recover host authority. Every host keeps at least one permanent custodian.</p>
              {people?.operators?.map((person: Record<string, any>) => <div className="ws-host-person" key={person.id}><span><strong>{person.name}</strong><small>{person.role} · {person.revoked_at ? 'Revoked' : person.expires_at ? `Until ${when(person.expires_at)}` : 'No expiry'}</small></span>{!person.revoked_at && <button className="ws-button" disabled={!!busy} onClick={() => setRevoke(person)}>Revoke</button>}</div>)}
              {people?.next_offset != null && <button className="ws-button" disabled={!!busy} onClick={() => void run('Reading more host identities…', async () => setPeople(await send('operators.list', { limit: 50, offset: people.next_offset })))}>More identities</button>}
              {revoke && <div className="ws-notice"><p>Revoke {revoke.name}’s host access? Queued work is cancelled. Work already past its approved service-change boundary may finish.</p><div className="ws-actions"><button className="ws-button" disabled={!!busy} onClick={() => void run('Revoking host access…', async () => { await send('operators.revoke', { operator_id: revoke.id, expected_revision: people?.revision ?? authority?.revision }); setRevoke(null); setPeople(await send('operators.list', { limit: 50 })); await refresh(profile.id) })}>Revoke this identity</button><button className="ws-button" onClick={() => setRevoke(null)}>Keep access</button></div></div>}
              <details><summary>Add another device, person or agent</summary><form onSubmit={event => { event.preventDefault(); void run('Granting reviewed host access…', async () => {
                const incoming = JSON.parse(grantText)
                if (!confirmGrant) throw new Error('Review the operator and role before granting access.')
                const result = await send('operators.grant', { expected_revision: people?.revision ?? authority?.revision,
                  operator: { name: incoming.name, public_key: incoming.public_key, role: grantRole, expires_at: grantExpiry ? new Date(grantExpiry).toISOString() : null } })
                setIssuedConnection({ ...profile.connection!, operator_id: result.operator_id, operator_key_fingerprint: result.fingerprint })
                setGrantText(''); setConfirmGrant(false); setPeople(await send('operators.list', { limit: 50 })); await refresh(profile.id)
              }) }}><label className="ws-field">Their public enrollment document<textarea rows={5} value={grantText} maxLength={2048} required onChange={event => { setGrantText(event.target.value); setConfirmGrant(false) }} /></label><label className="ws-field">Approved role<select value={grantRole} onChange={event => { setGrantRole(event.target.value); setConfirmGrant(false) }}><option value="observer">Observer</option><option value="operator">Operator</option><option value="custodian">Custodian</option></select></label><label className="ws-field">Access expiry (optional)<input type="datetime-local" value={grantExpiry} onChange={event => { setGrantExpiry(event.target.value); setConfirmGrant(false) }} /></label><label className="ws-checkbox"><input type="checkbox" checked={confirmGrant} onChange={event => setConfirmGrant(event.target.checked)} />I verified this recipient and approve the selected host role.</label><button className="ws-button ws-primary" disabled={!!busy || !confirmGrant || !grantText.trim()}>Grant host access</button></form></details>
              {issuedConnection && <div className="ws-notice"><h3>Send this connection to the new operator</h3><pre className="ws-code">{JSON.stringify(issuedConnection, null, 2)}</pre><button className="ws-button" onClick={() => void run('Copying the public connection…', () => copy(JSON.stringify(issuedConnection, null, 2)))}>Copy host connection</button></div>}
            </section>}
          </>}
          <details className="ws-card"><summary>Remove this login from this device</summary><p>Revoke the host grant first if this key should lose access. Removing its saved copy does not revoke it on the host.</p><label className="ws-checkbox"><input type="checkbox" checked={forget} onChange={event => setForget(event.target.checked)} />Remove this saved key and enrollment from this device.</label>{profile.last_operation && ['submitted', 'queued', 'running', 'inspection_required'].includes(profile.last_operation.phase) && <label className="ws-checkbox"><input type="checkbox" checked={acknowledgeOutstanding} onChange={event => setAcknowledgeOutstanding(event.target.checked)} />The last operation is unfinished. Keep its public recovery request before removing this key; I understand this does not cancel the operation.</label>}<button className="ws-button" disabled={!!busy || !forget} onClick={() => void run('Removing this device’s host login…', async () => { await api('host.forget', { id: profile.id, confirm: forget, acknowledge_outstanding: acknowledgeOutstanding }); await loadProfiles() })}>Remove saved login</button></details>
        </>}
      </div></div>
    </>}
  </main>
}
