import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ArrowRight, Building2, LoaderCircle, LockKeyhole, ShieldCheck } from 'lucide-react'
import type { InvitationPreview } from '@mnemion/client'
import type { Connection, WorkspaceSession } from './connection-types'
import { BrowserSignIn, browserCompanyConfiguration, browserCompanyStart, canRememberBrowser, joinLink, previewBrowserInvitation, type JoinLink } from './sign-in'
import type { CompanyConfiguration, CompanyCredentials } from '../../../shared/company-sign-in'
import { companyBrowserProof } from './company-browser'

type Target = { endpoint: string; workspaceId: string; configuration: CompanyConfiguration; invitation?: string; preview?: InvitationPreview }

export default function CompanySignIn({ incoming, initialEndpoint, secureStorage, busy, onBusy, onConnect, onNativeConnect, onBack }: {
  incoming: JoinLink | null; initialEndpoint: string; secureStorage: boolean; busy: boolean; onBusy: (label: string) => void
  onConnect: (connection: Connection) => void; onNativeConnect: (session: WorkspaceSession) => void; onBack?: () => void
}) {
  const desktop = window.mnemion?.workspaceCompanySignIn ? window.mnemion : undefined
  const [address, setAddress] = useState(incoming?.workspaceId ? incoming.endpoint + '/workspace?workspace=' + incoming.workspaceId : incoming?.endpoint ?? initialEndpoint)
  const [target, setTarget] = useState<Target>()
  const [provider, setProvider] = useState('')
  const [device, setDevice] = useState(desktop ? 'My computer' : 'My browser')
  const [remember, setRemember] = useState(!!desktop && secureStorage)
  const [error, setError] = useState<unknown>()
  const [opening, setOpening] = useState(false)
  const pending = useRef<AbortController | null>(null)
  const generation = useRef(0)
  const mayRemember = desktop ? secureStorage : canRememberBrowser()
  useEffect(() => () => { ++generation.current; pending.current?.abort(); if (desktop) void desktop.workspaceCompanyCancel?.() }, [desktop])

  async function inspect(event: FormEvent) {
    event.preventDefault()
    const attempt = ++generation.current
    onBusy('Checking company sign-in…'); setError(undefined)
    try {
      const link = joinLink(address)
      const invitation = link.invitation ?? (link.endpoint === incoming?.endpoint ? incoming.invitation : undefined)
      let preview: InvitationPreview | undefined
      if (invitation) preview = desktop?.workspaceInvitationPreview
        ? await desktop.workspaceInvitationPreview({ endpoint: link.endpoint, invitation }) : await previewBrowserInvitation(link.endpoint, invitation)
      if (preview && preview.purpose !== 'enroll') throw new Error('Use the password reset form for this invitation. Company access can be reapproved by your administrator.')
      const workspaceId = preview?.workspace_id ?? link.workspaceId
      if (!workspaceId) throw new Error('Use your administrator’s workspace sign-in link. It identifies your organization automatically.')
      const configuration = desktop?.workspaceCompanyConfiguration
        ? await desktop.workspaceCompanyConfiguration({ endpoint: link.endpoint, workspace_id: workspaceId }) : await browserCompanyConfiguration(link.endpoint, workspaceId)
      if (generation.current !== attempt) return
      if (!configuration.providers.length) throw new Error('Company sign-in is not enabled for this workspace. Use your personal login or ask your host operator to configure it.')
      setTarget({ endpoint: link.endpoint, workspaceId, configuration, invitation, preview })
      setProvider(configuration.providers[0].id)
    } catch (error) { if (generation.current === attempt) setError(error) }
    finally { if (generation.current === attempt) onBusy('') }
  }

  async function browserLogin(selected: Target, credentials: CompanyCredentials, controller: AbortController): Promise<Connection> {
    if (new URL(selected.endpoint).origin !== location.origin) throw new Error('Open this workspace’s own website to use company sign-in.')
    const proof = await companyBrowserProof(credentials.provider_id, signal => browserCompanyStart(selected.endpoint, {
      ...credentials, transport: 'browser', remember: remember && mayRemember,
    }, signal), controller)
    return BrowserSignIn.companySignIn(selected.endpoint, selected.workspaceId, proof, selected.preview)
  }

  async function signIn(event: FormEvent) {
    event.preventDefault()
    if (!target) return
    const attempt = ++generation.current, controller = new AbortController()
    pending.current = controller
    onBusy('Finish company sign-in in your browser…'); setOpening(true); setError(undefined)
    const credentials = { workspace_id: target.workspaceId, provider_id: provider, device_name: device,
      ...(target.invitation ? { invitation: target.invitation } : {}) }
    try {
      if (desktop?.workspaceCompanySignIn) {
        const session = await desktop.workspaceCompanySignIn({ endpoint: target.endpoint, credentials, remember: remember && mayRemember })
        if (generation.current === attempt) onNativeConnect(session)
        else if ((await desktop.workspaceStatus?.())?.active?.sessionToken === session.sessionToken) await desktop.workspaceDisconnect?.()
      } else {
        const connection = await browserLogin(target, credentials, controller)
        if (generation.current === attempt) onConnect(connection)
        else await connection.signOut?.().catch(() => {})
      }
    } catch (error) { if (generation.current === attempt) setError(error) }
    finally { if (generation.current === attempt) { pending.current = null; setOpening(false); onBusy('') } }
  }
  function cancel() {
    ++generation.current; pending.current?.abort(); pending.current = null
    if (desktop) void desktop.workspaceCompanyCancel?.()
    setOpening(false); onBusy('')
  }
  const chosen = target?.configuration.providers.find(item => item.id === provider)
  return <div className="ws-sign-in">
    <form onSubmit={target ? signIn : inspect} aria-label="Company sign-in">
      <p>Use your company’s existing account. Your administrator determines which memory spaces you can access.</p>
      {!target ? <><label className="ws-field"><span>Workspace sign-in link</span><input type={address.includes('#invitation=') ? 'password' : 'url'} value={address} onChange={event => setAddress(event.target.value)} required disabled={busy} autoComplete="off" spellCheck={false} placeholder="https://memory.example.com/workspace?workspace=…" /></label><small>You can also use your private invitation link.</small></> : <>
        <div className="ws-notice"><h3><ShieldCheck size={17} />{target.preview?.workspace_name ?? 'Your workspace'}</h3><small>{target.endpoint}</small>
          {target.preview && <><p>Join as <strong>{target.preview.person_name}</strong>{target.preview.administrator ? ' · Organization administrator' : ''}</p>
            {target.preview.spaces.length ? <ul>{target.preview.spaces.map(space => <li key={space.space_id}>{space.name} · {space.role}</li>)}</ul> : <p>No memory spaces have been assigned yet.</p>}</>}
        </div>
        {target.configuration.providers.length > 1 && <label className="ws-field"><span>Company account</span><select value={provider} onChange={event => setProvider(event.target.value)} disabled={busy}>{target.configuration.providers.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>}
        {chosen && <p><strong>{chosen.name}</strong><br /><small>{chosen.issuer}<br />Sign in again after {chosen.session_seconds % 3600 === 0 ? `${chosen.session_seconds / 3600} hours` : `${chosen.session_seconds / 60} minutes`}.</small></p>}
        <label className="ws-field"><span>Device name</span><input value={device} onChange={event => setDevice(event.target.value)} required maxLength={100} disabled={busy} /></label>
        <label className="ws-checkbox"><input type="checkbox" checked={remember && mayRemember} onChange={event => setRemember(event.target.checked)} disabled={busy || !mayRemember} />Remember this login on this device</label>
        <small className="ws-secure-note"><LockKeyhole size={15} />{desktop ? 'Company passwords stay with your identity provider. Saved sessions use your operating system’s secure store.' : 'Company passwords stay with your identity provider. Remembered sessions use a protected browser cookie.'}</small>
        <button type="button" className="ws-button ws-quiet" disabled={busy} onClick={() => setTarget(undefined)}>Use another workspace</button>
      </>}
      {!!error && <p className="ws-notice ws-error" role="alert">{error instanceof Error ? error.message.replace(/^Error invoking remote method '[^']+': (?:Error: )?/, '') : 'Company sign-in could not be completed.'}</p>}
      <button className="ws-button ws-primary" disabled={busy || !!target && !chosen}>{busy ? <LoaderCircle size={17} className="ws-spin" /> : target ? <Building2 size={17} /> : <ArrowRight size={17} />}{busy ? 'Please wait…' : target ? 'Continue with ' + chosen?.name : 'Check workspace'}</button>
    </form>
    {opening && <button type="button" className="ws-button ws-quiet" onClick={cancel}>Cancel company sign-in</button>}
    {onBack && <button type="button" className="ws-button ws-quiet" disabled={busy} onClick={onBack}>Use a password instead</button>}
  </div>
}
