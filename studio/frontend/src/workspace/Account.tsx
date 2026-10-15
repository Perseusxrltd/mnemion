import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Copy, KeyRound, RefreshCw, ShieldCheck } from 'lucide-react'
import { MnemionError, type InvitationReceipt } from '@mnemion/client'
import type { Connection } from './connection-types'
import CompanyAccess from './CompanyAccess'

const date = (value: string) => new Date(value).toLocaleString()
function CopyValue({ value, label }: { value: string; label: string }) {
  const [copied, setCopied] = useState<string>()
  const [failed, setFailed] = useState<string>()
  async function copy() {
    try { await navigator.clipboard.writeText(value); setCopied(value); setFailed(undefined) }
    catch { setCopied(undefined); setFailed(value) }
  }
  return <><button type="button" className="ws-button ws-quiet" onClick={() => void copy()}><Copy size={14} />{copied === value ? 'Copied' : label}</button>{failed === value && <small>Select and copy the value manually; clipboard access is unavailable.</small>}</>
}

export default function Account({ connection, disconnect }: { connection: Connection; disconnect: () => void }) {
  const { client, me, endpoint } = connection
  const cache = useQueryClient()
  const account = useQuery({ queryKey: ['password-account'], queryFn: () => client.passwordAccount() })
  const signInConfiguration = useQuery({ queryKey: ['sign-in-configuration', endpoint], queryFn: () => client.signInConfiguration(), enabled: account.isSuccess, retry: false })
  const sessions = useQuery({ queryKey: ['device-sessions'], queryFn: () => client.deviceSessions() })
  const apps = useQuery({ queryKey: ['oauth-connections'], queryFn: () => client.oauthConnections(), enabled: account.isSuccess,
    retry: (count, error) => !(error instanceof MnemionError && error.status === 404) && count < 1 })
  const people = useQuery({ queryKey: ['account-people'], queryFn: () => client.principals(), enabled: me.administrator })
  const invitations = useQuery({ queryKey: ['sign-in-invitations'], queryFn: () => client.signInInvitations(), enabled: me.administrator })
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [currentPassword, setCurrentPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [person, setPerson] = useState('')
  const [purpose, setPurpose] = useState<'enroll' | 'reset'>('enroll')
  const [expiry, setExpiry] = useState(86400)
  const [issued, setIssued] = useState<InvitationReceipt>()
  const [pendingRevoke, setPendingRevoke] = useState<string>()
  const [pendingApp, setPendingApp] = useState<string>()
  const [allPeople, setAllPeople] = useState(false)
  const [allApps, setAllApps] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>()
  const [notice, setNotice] = useState('')
  const [passwordFormRevision, setPasswordFormRevision] = useState(0)
  const [invitationFormRevision, setInvitationFormRevision] = useState(0)
  useEffect(() => { setUsername(account.data?.account?.username ?? '') }, [account.data?.account?.username])
  const unsupported = account.error instanceof MnemionError && account.error.status === 404
  let signInOrigin = endpoint
  try {
    const configured = new URL(signInConfiguration.data?.public_origin ?? endpoint)
    if (configured.protocol === 'https:' && !configured.username && !configured.password && configured.pathname === '/' && !configured.search && !configured.hash) signInOrigin = configured.origin
  } catch { /* An invalid optional origin cannot replace the connected address. */ }
  const signInLink = signInOrigin + '/workspace?workspace=' + me.tenant_id
  const humans = people.data?.items.filter(p => p.kind === 'human' && !p.disabled_at) ?? []
  const appSessions = new Set(apps.data?.connections.map(app => app.session_id) ?? [])
  const visibleSessions = (sessions.data?.items ?? []).filter(s => !appSessions.has(s.id) && (allPeople || s.principal_id === me.principal_id))
  const visibleApps = (apps.data?.connections ?? []).filter(app => allApps || app.principal_id === me.principal_id)
  async function run(action: () => Promise<void>, refresh = true) {
    setBusy(true); setError(undefined); setNotice('')
    try {
      await action()
      if (refresh) await Promise.all([
        cache.invalidateQueries({ queryKey: ['password-account'] }),
        cache.invalidateQueries({ queryKey: ['device-sessions'] }),
        cache.invalidateQueries({ queryKey: ['oauth-connections'] }),
        cache.invalidateQueries({ queryKey: ['sign-in-invitations'] }),
      ])
    } catch (error) { setError(error) } finally { setBusy(false) }
  }
  async function changePassword(event: FormEvent) {
    event.preventDefault()
    if (password !== confirm) { setError(new Error('Enter the same password twice.')); return }
    await run(async () => {
      await client.setPassword({ username, password, ...(account.data?.account ? { current_password: currentPassword } : {}) })
      setPassword(''); setCurrentPassword(''); setConfirm('')
      setPasswordFormRevision(value => value + 1)
      setNotice('Login saved. Device sessions have been signed out. Your independent API keys remain available.')
      if (!!connection.authentication) disconnect()
    }, !connection.authentication)
  }
  const sessionToRevoke = sessions.data?.items.find(s => s.id === pendingRevoke)
  const appToRevoke = apps.data?.connections.find(app => app.session_id === pendingApp)
  return <div className="ws-page">
    <header className="ws-page-heading"><div><p className="ws-eyebrow">Your access</p><h1>Account & sessions</h1>
      <p>Use your own login on every device. Keep recovery access and assistant keys independently controlled.</p></div></header>
    {unsupported ? <div className="ws-notice"><p>This workspace server needs an update before it can manage individual logins. Your existing connection remains usable.</p><Link to="/workspace/setup" className="ws-button">Workspace setup</Link></div> : <>
    {!!(error || account.error || sessions.error || invitations.error || people.error) && <div className="ws-notice ws-error" role="alert">
      {(() => { const value = error || account.error || sessions.error || invitations.error || people.error; return value instanceof Error ? value.message : 'The request could not be completed.' })()}
    </div>}
    {notice && <div className="ws-notice" role="status">{notice}</div>}
    <section className="ws-card"><h2><ShieldCheck size={19} /> Your workspace sign-in link</h2><p>Share this address with people who already have a login. It contains no password or memory key.</p>
      <div className="ws-code"><code>{signInLink}</code><CopyValue value={signInLink} label="Copy sign-in link" /></div>
      <small>The host must be reachable from their device. A local address is only reachable on this computer. Use the host’s public HTTPS address to invite people on other computers.</small>
    </section>
    <CompanyAccess connection={connection} people={humans} disconnect={disconnect} />
    {account.data?.can_use_password ? <form key={passwordFormRevision} className="ws-card ws-form" onSubmit={changePassword}>
      <h2>{account.data.account ? 'Change your login or password' : 'Create your personal login'}</h2>
      {account.data.account?.reset_required ? <p className="ws-notice">An administrator must issue a new reset invitation for this account.</p> : <>
        <label className="ws-field"><span>Login name</span><input value={username} onChange={event => setUsername(event.target.value)} required minLength={3} maxLength={128} autoComplete="username" autoCapitalize="none" spellCheck={false} disabled={busy} /></label>
        {account.data.account && <label className="ws-field"><span>Current password</span><input type="password" value={currentPassword} onChange={event => setCurrentPassword(event.target.value)} required autoComplete="current-password" disabled={busy} /></label>}
        <label className="ws-field"><span>New password</span><input type="password" value={password} onChange={event => setPassword(event.target.value)} required minLength={15} maxLength={128} autoComplete="new-password" disabled={busy} /></label>
        <small>Use at least 15 characters, such as several unrelated words.</small>
        <label className="ws-field"><span>Confirm new password</span><input type="password" value={confirm} onChange={event => setConfirm(event.target.value)} required autoComplete="new-password" disabled={busy} /></label>
        <p className="ws-helper">Saving signs out all of your device sessions. Keep your independent recovery key in a safe place.</p>
        <button className="ws-button ws-primary" disabled={busy || !password}><KeyRound size={16} />Save login</button>
      </>}
    </form> : account.data && <div className="ws-card"><p>This connection belongs to an application. Applications use their own keys or linked identity-provider credentials; people use individual accounts.</p></div>}
    <section className="ws-card"><div className="ws-section-title"><h2>Device sessions</h2><button type="button" className="ws-button ws-quiet" disabled={busy || sessions.isFetching} onClick={() => void sessions.refetch()}><RefreshCw size={14} />Refresh</button></div>
      <p>Revoke a lost or unused device without affecting your other sessions.</p>
      {me.administrator && <label className="ws-checkbox"><input type="checkbox" data-update-safe checked={allPeople} onChange={event => setAllPeople(event.target.checked)} />Show everyone in this organization</label>}
      <div className="ws-table-wrap"><table className="ws-table"><thead><tr><th>Device</th><th>Person</th><th>Last renewed</th><th>Expires</th><th>Access</th></tr></thead>
        <tbody>{visibleSessions.map(session => <tr key={session.id}><td><strong>{session.device_name}{session.current ? ' · This session' : ''}</strong><small>{session.authentication === 'company' ? 'Company account' : 'Personal password'} · {session.transport} · Created {date(session.created_at)}</small></td>
          <td>{session.principal_id === me.principal_id ? me.name : humans.find(p => p.id === session.principal_id)?.name ?? session.principal_id}</td>
          <td>{date(session.last_refreshed_at)}</td><td>{date(session.expires_at)}</td><td>{session.revoked_at ? 'Revoked' : Date.parse(session.expires_at) <= Date.now() ? 'Expired' :
            <button type="button" className="ws-button ws-quiet" disabled={busy} onClick={() => setPendingRevoke(session.id)}>Revoke session</button>}</td></tr>)}</tbody>
      </table></div>
      {!sessions.isPending && visibleSessions.length === 0 && <p>No device sessions to show.</p>}
      <small>Device names are labels supplied at sign-in. Last renewed records credential refresh, not every memory request.</small>
      {(sessions.data?.items.length ?? 0) >= 1000 && <p>Showing the latest 1,000 sessions returned by the server.</p>}
      {sessionToRevoke && <div className="ws-notice" role="group" aria-label="Confirm session revocation">
        <p>Revoke <strong>{sessionToRevoke.device_name}</strong>?{sessionToRevoke.current ? ' You will be signed out here.' : ' That device will need to sign in again.'}</p>
        <button type="button" className="ws-button" disabled={busy} onClick={() => void run(async () => {
          await client.revokeSession(sessionToRevoke.id); setPendingRevoke(undefined)
          if (sessionToRevoke.current) disconnect(); else setNotice('The device session has been revoked.')
        }, !sessionToRevoke.current)}>Revoke access</button><button type="button" className="ws-button ws-quiet" disabled={busy} onClick={() => setPendingRevoke(undefined)}>Keep session</button>
      </div>}
    </section>
    {apps.data && <section className="ws-card"><div className="ws-section-title"><h2>Connected apps</h2><button type="button" className="ws-button ws-quiet" disabled={busy || apps.isFetching} onClick={() => void apps.refetch()}><RefreshCw size={14} />Refresh</button></div>
      <p>Apps you approved use your account’s permissions. Revoking an app ends its access immediately; your other connections keep working.</p>
      {me.administrator && <label className="ws-checkbox"><input type="checkbox" data-update-safe checked={allApps} onChange={event => setAllApps(event.target.checked)} />Show everyone’s connected apps</label>}
      <div className="ws-table-wrap"><table className="ws-table"><thead><tr><th>App</th><th>Person</th><th>Last renewed</th><th>Expires</th><th>Access</th></tr></thead><tbody>
        {visibleApps.map(app => <tr key={app.session_id}><td><strong>{app.device_name.replace(/^Agent: /, '')}</strong><small>Connected {date(app.created_at)}</small></td><td>{app.principal_id === me.principal_id ? me.name : humans.find(person => person.id === app.principal_id)?.name ?? app.principal_id}</td><td>{date(app.last_refreshed_at)}</td><td>{date(app.expires_at)}</td><td>{app.revoked_at ? 'Revoked' : Date.parse(app.expires_at) <= Date.now() ? 'Expired' : <button type="button" className="ws-button ws-quiet" disabled={busy} onClick={() => setPendingApp(app.session_id)}>Revoke app</button>}</td></tr>)}
      </tbody></table></div>
      {visibleApps.length === 0 && <p>No connected apps to show.</p>}
      {apps.data.connections.length >= 1000 && <p>Showing the latest 1,000 app connections returned by the server.</p>}
      {appToRevoke && <div className="ws-notice" role="group" aria-label="Confirm app revocation"><p>Revoke <strong>{appToRevoke.device_name.replace(/^Agent: /, '')}</strong>? It will need a new approval before connecting again.</p>
        <button type="button" className="ws-button" disabled={busy} onClick={() => void run(async () => { await client.revokeOAuthConnection(appToRevoke.session_id); setPendingApp(undefined); setNotice('The app connection has been revoked.') })}>Revoke access</button><button type="button" className="ws-button ws-quiet" disabled={busy} onClick={() => setPendingApp(undefined)}>Keep connection</button></div>}
    </section>}
    {apps.error && !(apps.error instanceof MnemionError && apps.error.status === 404) && <div className="ws-notice ws-error" role="alert">Connected apps could not be loaded. <button type="button" className="ws-button ws-quiet" onClick={() => void apps.refetch()}>Retry</button></div>}
    {me.administrator && <>
      <form key={invitationFormRevision} className="ws-card ws-form" onSubmit={event => {
        event.preventDefault()
        void run(async () => {
          setIssued(await client.createSignInInvitation({ principal_id: person, purpose, expires_in_seconds: expiry }))
          setPerson(''); setPurpose('enroll'); setExpiry(86400)
          setInvitationFormRevision(value => value + 1)
        })
      }}><h2>Invite a person or reset their login</h2>
        <p>Choose a person whose space permissions are already set. They can create a personal password or join with an enabled company account.</p>
        <Link className="ws-link" to="/workspace/team">Create a person or change their space access</Link>
        <label className="ws-field"><span>Person</span><select value={person} onChange={event => setPerson(event.target.value)} required disabled={busy}><option value="">Choose a person</option>{humans.map(p => <option key={p.id} value={p.id}>{p.name}{p.administrator ? ' · Organization administrator' : ''}</option>)}</select></label>
        <label className="ws-field"><span>Invitation type</span><select value={purpose} onChange={event => setPurpose(event.target.value as 'enroll' | 'reset')} disabled={busy}><option value="enroll">First login</option><option value="reset">Reset existing login</option></select></label>
        {purpose === 'reset' && <p className="ws-notice">Creating this reset immediately disables the old password and signs out that person’s device sessions. Independent API keys remain valid. Revoke a linked company identity separately to prevent another company sign-in.</p>}
        <label className="ws-field"><span>Expires after</span><select value={expiry} onChange={event => setExpiry(Number(event.target.value))} disabled={busy}><option value={3600}>1 hour</option><option value={86400}>1 day</option><option value={604800}>7 days</option></select></label>
        <button className="ws-button ws-primary" disabled={busy || !person}>Create private invitation</button>
      </form>
      {issued && <section className="ws-card" aria-label="New private invitation" data-update-pending><h2>Share privately with {issued.preview?.person_name ?? 'the selected person'}</h2>
        <p>This invitation can be used once, before {date(issued.expires_at)}. A newer invitation or a permission change invalidates it.</p>
        {issued.preview && <><p>{issued.preview.administrator ? 'Organization administrator' : 'Member'}</p><ul>{issued.preview.spaces.map(space => <li key={space.space_id}>{space.name} · {space.role}</li>)}</ul></>}
        <label className="ws-field"><span>{issued.invitation_url ? 'Private invitation link' : 'Private invitation code'}</span><input type="password" readOnly value={issued.invitation_url ?? issued.invitation_token} autoComplete="off" /></label>
        <CopyValue value={issued.invitation_url ?? issued.invitation_token} label="Copy private invitation" />
        {!issued.invitation_url && <p>Share this code with the workspace address for use in the desktop app. The host operator must configure a public HTTPS address to create browser invitation links.</p>}
        <button type="button" className="ws-button ws-quiet" onClick={() => setIssued(undefined)}>I have shared it securely</button>
      </section>}
      <section className="ws-card"><h2>Organization invitations</h2><div className="ws-table-wrap"><table className="ws-table"><thead><tr><th>Person</th><th>Purpose</th><th>Expires</th><th>Status</th></tr></thead>
        <tbody>{invitations.data?.items.map(invite => <tr key={invite.id}><td>{humans.find(p => p.id === invite.principal_id)?.name ?? invite.principal_id}</td><td>{invite.purpose}</td><td>{date(invite.expires_at)}</td><td>{invite.consumed_at ? 'Accepted' : invite.revoked_at ? 'Revoked' : Date.parse(invite.expires_at) <= Date.now() ? 'Expired' :
          <button type="button" className="ws-button ws-quiet" disabled={busy} onClick={() => void run(async () => { await client.revokeSignInInvitation(invite.id); if (issued?.id === invite.id) setIssued(undefined); setNotice('Invitation revoked.') })}>Revoke invitation</button>}</td></tr>)}</tbody>
      </table></div></section>
    </>}
    </>}
  </div>
}
