import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ArrowRight, KeyRound, LoaderCircle, LockKeyhole, ShieldCheck } from 'lucide-react'
import type { InvitationPreview } from '@mnemion/client'
import type { Connection, WorkspaceSession } from './connection-types'
import { BrowserSignIn, browserBookmarks, canRememberBrowser, forgetBrowserBookmark, joinLink, previewBrowserInvitation, type JoinLink } from './sign-in'
import CompanySignIn from './CompanySignIn'

export default function SignInForm({ method, incoming, initialEndpoint, initialError, secureStorage, busy, onBusy, onConnect, onNativeConnect }: {
  method: 'password' | 'invitation'; incoming: JoinLink | null; initialEndpoint: string
  initialError?: unknown
  secureStorage: boolean; busy: boolean; onBusy: (value: string) => void
  onConnect: (connection: Connection) => void; onNativeConnect: (session: WorkspaceSession) => void
}) {
  const desktop = window.mnemion?.workspaceSignIn ? window.mnemion : undefined
  const [address, setAddress] = useState(incoming?.workspaceId
    ? incoming.endpoint + '/workspace?workspace=' + incoming.workspaceId : incoming?.endpoint ?? initialEndpoint)
  const [invitation, setInvitation] = useState(incoming?.invitation ?? '')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [device, setDevice] = useState(desktop ? 'My computer' : 'My browser')
  const [remember, setRemember] = useState(!!desktop && secureStorage)
  const [preview, setPreview] = useState<InvitationPreview>()
  const [previewEndpoint, setPreviewEndpoint] = useState('')
  const [previewSecret, setPreviewSecret] = useState('')
  const [error, setError] = useState<unknown>(initialError)
  const [company, setCompany] = useState(false)
  useEffect(() => { if (initialError) setError(initialError) }, [initialError])
  const [saved, setSaved] = useState(browserBookmarks)
  const mounted = useRef(true)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  const mayRemember = desktop ? secureStorage : canRememberBrowser()

  async function run(label: string, action: () => Promise<void>) {
    onBusy(label); setError(undefined)
    try { await action() } catch (error) { if (mounted.current) setError(error) }
    finally { if (mounted.current) { setSaved(browserBookmarks()); onBusy('') } }
  }
  function target(): JoinLink {
    if (method === 'invitation' && /^https?:\/\//i.test(invitation.trim())) return joinLink(invitation)
    const value = joinLink(address)
    return method === 'invitation' ? { ...value, invitation: invitation.trim() || value.invitation } : value
  }
  async function inspect(event: FormEvent) {
    event.preventDefault()
    await run('Checking your invitation and access…', async () => {
      const parsed = target()
      if (!parsed.invitation) throw new Error('Paste your invitation link or private invitation code.')
      const data = desktop?.workspaceInvitationPreview
        ? await desktop.workspaceInvitationPreview({ endpoint: parsed.endpoint, invitation: parsed.invitation })
        : await previewBrowserInvitation(parsed.endpoint, parsed.invitation)
      if (!mounted.current) return
      setPreview(data); setPreviewEndpoint(parsed.endpoint); setPreviewSecret(parsed.invitation)
      setUsername(data.suggested_login ?? '')
      setAddress(parsed.endpoint)
    })
  }
  async function submit(event: FormEvent) {
    event.preventDefault()
    await run(method === 'invitation' ? 'Creating your login…' : 'Signing in…', async () => {
      const parsed = target()
      if (method === 'invitation' && (!preview || password !== confirm)) throw new Error('Enter the same password twice.')
      if (method === 'password' && !parsed.workspaceId) throw new Error('Use the workspace sign-in link from your administrator. It identifies your organization automatically.')
      const endpoint = method === 'invitation' ? previewEndpoint : parsed.endpoint
      const common = { username, password, device_name: device }
      if (desktop?.workspaceSignIn && desktop.workspaceInvitationAccept) {
        const session = method === 'invitation'
          ? await desktop.workspaceInvitationAccept({ endpoint, credentials: { ...common, invitation: previewSecret }, remember: remember && mayRemember })
          : await desktop.workspaceSignIn({ endpoint, credentials: { ...common, workspace_id: parsed.workspaceId! }, remember: remember && mayRemember })
        if (!mounted.current) return
        setPassword(''); setConfirm(''); setInvitation(''); setPreviewSecret('')
        onNativeConnect(session)
      } else {
        const connection = await BrowserSignIn.signIn(endpoint, method === 'invitation'
          ? { ...common, invitation: previewSecret } : { ...common, workspace_id: parsed.workspaceId! },
          remember && mayRemember, method === 'invitation' ? preview : undefined)
        if (!mounted.current) { connection.close?.(); return }
        setPassword(''); setConfirm(''); setInvitation(''); setPreviewSecret('')
        onConnect(connection)
      }
    })
  }
  const foreignOrigin = !desktop && (() => { try { return new URL(target().endpoint).origin !== location.origin } catch { return false } })()
  if (company && preview) return <CompanySignIn incoming={{ endpoint: previewEndpoint, workspaceId: preview.workspace_id, invitation: previewSecret }} initialEndpoint={previewEndpoint} secureStorage={secureStorage} busy={busy} onBusy={onBusy} onConnect={onConnect} onNativeConnect={onNativeConnect} onBack={() => setCompany(false)} />
  return <div className="ws-sign-in">
    {!desktop && saved.length > 0 && method === 'password' && <section className="ws-saved-workspaces" aria-label="Remembered browser logins">
      <h3>Continue in your workspace</h3>
      {saved.map(bookmark => <div className="ws-saved-workspace" key={bookmark.sessionId}>
        <div><strong>{bookmark.workspaceName}</strong><span>{bookmark.name}</span><small>{bookmark.endpoint}</small></div>
        <div className="ws-saved-actions">
          <button type="button" className="ws-button ws-primary" disabled={busy || bookmark.refreshPending || Date.parse(bookmark.expiresAt) <= Date.now()}
            onClick={() => void run('Reopening your login…', async () => {
              const connection = await BrowserSignIn.resume(bookmark)
              if (mounted.current) onConnect(connection); else connection.close?.()
            })}>Continue</button>
          <button type="button" className="ws-button ws-quiet" disabled={busy} onClick={() => {
            forgetBrowserBookmark(bookmark); setSaved(browserBookmarks())
            setAddress(bookmark.endpoint + '/workspace?workspace=' + bookmark.workspaceId)
          }}>Use a new login</button>
        </div>
        {(bookmark.refreshPending || Date.parse(bookmark.expiresAt) <= Date.now()) && <small>Sign in again to renew this device’s access.</small>}
      </div>)}
    </section>}
    <form onSubmit={method === 'invitation' && !preview ? inspect : submit} aria-label={method === 'invitation' ? 'Accept a workspace invitation' : 'Sign in to a workspace'}>
      {!preview && <>
        <label className="ws-field"><span>{method === 'password' ? 'Workspace sign-in link' : 'Workspace address'}</span>
          <input type="url" value={address} onChange={event => setAddress(event.target.value)} disabled={busy} required autoComplete="url" placeholder="https://memory.example.com/workspace?workspace=…" /></label>
        <small>{method === 'password' ? 'Your administrator’s link identifies the workspace. Your login identifies you.' : 'Paste a complete invitation below; its address takes precedence.'}</small>
        {method === 'invitation' && <label className="ws-field"><span>Private invitation link or code</span>
          <input type="password" value={invitation} onChange={event => setInvitation(event.target.value)} disabled={busy} required autoComplete="off" spellCheck={false} /></label>}
      </>}
      {preview && <div className="ws-notice">
        <h3><ShieldCheck size={17} /> Join {preview.workspace_name}</h3>
        <p>Signing in as <strong>{preview.person_name}</strong></p><small>{previewEndpoint}</small>
        <p>{preview.administrator ? 'Organization administrator: can manage people and workspace access.' : 'Member: access is limited to the spaces shown below.'}</p>
        {preview.spaces.length ? <ul>{preview.spaces.map(space => <li key={space.space_id}><strong>{space.name}</strong> · {space.role}</li>)}</ul> : <p>No memory spaces have been granted yet. Ask your administrator to assign access.</p>}
        <small>Invitation expires {new Date(preview.expires_at).toLocaleString()}.</small>
        {preview.purpose === 'enroll' && <button type="button" className="ws-button" disabled={busy} onClick={() => setCompany(true)}>Join with my company account</button>}
        <button type="button" className="ws-button ws-quiet" disabled={busy} onClick={() => { setPreview(undefined); setPassword(''); setConfirm(''); }}>Use a different invitation</button>
      </div>}
      {(method === 'password' || preview) && <>
        <label className="ws-field"><span>Login name</span><input value={username} onChange={event => setUsername(event.target.value)} required minLength={3} maxLength={128} disabled={busy} autoComplete="username" autoCapitalize="none" spellCheck={false} /></label>
        <label className="ws-field"><span>{preview ? 'Choose your password' : 'Password'}</span><input type="password" value={password} onChange={event => setPassword(event.target.value)} required minLength={preview ? 15 : 1} maxLength={256} disabled={busy} autoComplete={preview ? 'new-password' : 'current-password'} /></label>
        {preview && <>
          <small>Use at least 15 characters. Several unrelated words work well. Your administrator cannot see your password.</small>
          <label className="ws-field"><span>Confirm password</span><input type="password" value={confirm} onChange={event => setConfirm(event.target.value)} required disabled={busy} autoComplete="new-password" /></label>
        </>}
        <label className="ws-field"><span>Device name</span><input value={device} onChange={event => setDevice(event.target.value)} required maxLength={100} disabled={busy} autoComplete="off" /></label>
        <small>A label you can recognize later in Account & sessions.</small>
        <label className="ws-checkbox"><input type="checkbox" checked={remember && mayRemember} onChange={event => setRemember(event.target.checked)} disabled={busy || !mayRemember} />Remember this login on this device</label>
        <small className="ws-secure-note"><LockKeyhole size={15} />{desktop
          ? mayRemember ? 'Saved logins use your operating system’s secure store.' : 'Unlock your operating system’s secure store to remember a login.'
          : mayRemember ? 'Your browser keeps a protected login cookie. Passwords are never saved by Mnemion.' : 'This login stays in the window. Remembered browser logins require HTTPS and a supported browser.'}</small>
      </>}
      {foreignOrigin && <div className="ws-notice"><p>Open this workspace’s own website to sign in securely.</p><a className="ws-button" href={(() => { try { const p = target(); return p.endpoint + '/workspace' + (p.workspaceId ? '?workspace=' + p.workspaceId : '') + (p.invitation ? '#invitation=' + p.invitation : '') } catch { return undefined } })()} rel="noreferrer">Open workspace website <ArrowRight size={15} /></a></div>}
      {!!error && <p className="ws-notice ws-error" role="alert">{error instanceof Error ? error.message.replace(/^Error invoking remote method '[^']+': (?:Error: )?/, '') : 'Sign-in could not be completed.'}</p>}
      <button className="ws-button ws-primary" disabled={busy || foreignOrigin}>
        {busy ? <LoaderCircle size={17} className="ws-spin" /> : <KeyRound size={17} />}
        {busy ? 'Please wait…' : method === 'invitation' ? preview ? 'Create my login and open workspace' : 'Review invitation' : 'Sign in'}
      </button>
      {method === 'password' && <p><small>Forgot your password? Ask an organization administrator for a fresh reset invitation. Existing agent keys continue to work independently.</small></p>}
    </form>
  </div>
}
