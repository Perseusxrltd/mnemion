import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ArrowRight, Building2, LoaderCircle, ShieldCheck } from 'lucide-react'
import BrandMark from '../components/BrandMark'
import type { CompanyConfiguration } from '../../../shared/company-sign-in'
import { companyConfiguration } from '../../../electron/company-sign-in-protocol'
import { companyBrowserProof } from './company-browser'
import './workspace.css'

type RequestDetails = { client_name: string; callback: string; csrf: string; expires_at: number; company: CompanyConfiguration }
type PermissionReview = {
  proof: string
  authentication: 'password' | 'company'
  expires_at?: string
  permissions: {
    name: string; workspace_name: string; administrator: boolean; space_count: number
    spaces: Array<{ id: string; name: string; role: string }>
  }
}

async function consent<T>(action: string, body: object, csrf?: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`/oauth/consent/${action}`, {
    method: 'POST', credentials: 'same-origin', cache: 'no-store', redirect: 'error',
    headers: { 'Content-Type': 'application/json', ...(csrf ? { 'X-Mnemion-Consent-CSRF': csrf } : {}) },
    body: JSON.stringify(body), signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(20000)]) : AbortSignal.timeout(20000),
  })
  const result = await response.json()
  if (!response.ok) throw new Error(result?.error?.message || 'The connection could not be completed. Start again from your app.')
  return result as T
}

export default function HostedConsent() {
  const [ticket] = useState(() => {
    const value = new URLSearchParams(window.location.hash.slice(1)).get('request') ?? ''
    return /^mnm_ot_[A-Za-z0-9_-]{43}$/.test(value) ? value : ''
  })
  const opening = useRef<Promise<RequestDetails> | undefined>(undefined)
  const pendingCompany = useRef<AbortController | null>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  const [details, setDetails] = useState<RequestDetails>()
  const [review, setReview] = useState<PermissionReview>()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [provider, setProvider] = useState('')
  const [companyOpening, setCompanyOpening] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => { if (review) heading.current?.focus() }, [review])
  useEffect(() => () => { pendingCompany.current?.abort(); pendingCompany.current = null }, [])
  useEffect(() => {
    const previous = document.title
    document.title = 'Connect your app · Mnemion'
    return () => { document.title = previous }
  }, [])
  useEffect(() => {
    // Keep the one-time request in memory, out of history and browser storage.
    window.history.replaceState(window.history.state, '', window.location.pathname + window.location.search)
    if (!ticket) return
    let active = true
    opening.current ??= consent<RequestDetails>('request', { ticket })
    void opening.current.then(value => {
      if (!active) return
      const company = companyConfiguration(value.company ?? { providers: [], callback_uri: null }, window.location.origin)
      setDetails({ ...value, company }); setProvider(company.providers[0]?.id ?? '')
    })
      .catch(value => { if (active) setError(value instanceof Error ? value.message : 'Restart this connection from your app.') })
    return () => { active = false }
  }, [ticket])

  async function run(action: () => Promise<void>) {
    if (busy) return
    setBusy(true); setError('')
    try { await action() }
    catch (value) { setError(value instanceof Error ? value.message : 'The connection could not be completed.') }
    finally { setBusy(false) }
  }
  function returnToApp(location: string) {
    const target = new URL(location), callback = new URL(details!.callback)
    if (target.origin !== callback.origin || target.pathname !== callback.pathname || target.username || target.password || target.hash || target.searchParams.get('iss') !== window.location.origin + '/') {
      throw new Error('The return address changed. Restart the connection from your app.')
    }
    window.location.assign(target.href)
  }
  async function login(event: FormEvent) {
    event.preventDefault()
    const submitted = password
    setPassword('')
    await run(async () => setReview(await consent<PermissionReview>('login', { ticket, username, password: submitted }, details!.csrf)))
  }
  async function companyLogin() {
    if (busy || !details || !provider) return
    const controller = new AbortController()
    pendingCompany.current = controller
    setPassword(''); setCompanyOpening(true)
    try {
      await run(async () => {
        const proof = await companyBrowserProof(provider, signal => consent('company/start', {
          ticket, provider_id: provider,
        }, details.csrf, signal), controller)
        const result = await consent<PermissionReview>('company/finish', { ticket, ...proof }, details.csrf, controller.signal)
        if (!controller.signal.aborted && pendingCompany.current === controller) setReview(result)
      })
    } finally {
      if (pendingCompany.current === controller) { pendingCompany.current = null; setCompanyOpening(false) }
    }
  }
  async function approve() {
    await run(async () => {
      const result = await consent<{ redirect: string }>('approve', { ticket, proof: review!.proof }, details!.csrf)
      setReview(undefined); returnToApp(result.redirect)
    })
  }
  async function cancel() {
    await run(async () => {
      const result = await consent<{ redirect: string }>('cancel', { ticket }, details!.csrf)
      setReview(undefined); setPassword(''); returnToApp(result.redirect)
    })
  }
  const permissions = review?.permissions
  const chosenCompany = details?.company.providers.find(item => item.id === provider)
  return <main className="workspace ws-hosted-consent">
    <div className="ws-consent-container">
      <a href="/workspace" className="ws-consent-brand"><BrandMark /><span>Mnemion</span></a>
      <section className="ws-card">
        <p className="ws-eyebrow">Your memory. Your permission.</p>
        <h1 ref={heading} tabIndex={-1}>{permissions ? 'Review access' : 'Connect your app'}</h1>
        {(!ticket || error) && <div className="ws-notice ws-error" role="alert">{error || 'Open a new connection from the app you want to use. This link is incomplete or has expired.'}</div>}
        {ticket && !details && !error && <p role="status">Opening your connection…</p>}
        {details && <>
          <div className="ws-consent-app"><strong>{details.client_name}</strong><span>{new URL(details.callback).host}</span></div>
          <p>Check that this is the app you meant to connect. Its name is provided by the app; the address above is where you will return.</p>
          {!permissions ? <>
            {chosenCompany && <div className="ws-sign-in">
              <p>Use your company account to review what this app can access.</p>
              {details.company.providers.length > 1 && <label className="ws-field"><span>Company account</span><select value={provider} onChange={event => setProvider(event.target.value)} disabled={busy}>{details.company.providers.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>}
              <button type="button" className="ws-button ws-primary" disabled={busy} onClick={() => void companyLogin()}>{companyOpening ? <LoaderCircle size={17} className="ws-spin" /> : <Building2 size={17} />}{companyOpening ? 'Finish company sign-in in the other window…' : 'Continue with ' + chosenCompany.name}</button>
              {companyOpening && <button type="button" className="ws-button ws-quiet" onClick={() => pendingCompany.current?.abort()}>Cancel company sign-in</button>}
              <p className="ws-helper">Your company must already have given you workspace access. This connection lasts up to {chosenCompany.session_seconds / 3600} hours before you sign in again.</p>
            </div>}
            <form className="ws-form" onSubmit={login}>
            <p>{chosenCompany ? 'Or use your personal workspace login.' : 'Sign in with your personal workspace login to review what this app can access.'}</p>
            <label className="ws-field"><span>Login name</span><input value={username} onChange={event => setUsername(event.target.value)} autoComplete="username" autoCapitalize="none" spellCheck={false} required minLength={3} maxLength={128} disabled={busy} /></label>
            <label className="ws-field"><span>Password</span><input type="password" value={password} onChange={event => setPassword(event.target.value)} autoComplete="current-password" required maxLength={128} disabled={busy} /></label>
            <p className="ws-helper">Need a login or a password reset? Ask a workspace administrator for an invitation.</p>
            <div className="ws-setup-actions"><button type="button" className="ws-button ws-quiet" onClick={() => void cancel()} disabled={busy}>Cancel</button><button className="ws-button ws-primary" disabled={busy}>{busy ? 'Signing in…' : 'Review access'}<ArrowRight size={16} /></button></div>
          </form></> : <div>
            <div className="ws-consent-person"><ShieldCheck size={22} /><div><strong>{permissions.name}</strong><span>{permissions.workspace_name}</span></div></div>
            <p><strong>{details.client_name}</strong> will act with this account’s permissions. It can keep working when you close this page.</p>
            {review?.authentication === 'company' && review.expires_at && <div className="ws-notice"><strong>Company sign-in</strong><p>This connection expires {new Date(review.expires_at).toLocaleString()}. The app must ask you to sign in again after that. Your workspace administrator can revoke it sooner.</p></div>}
            {permissions.administrator && <div className="ws-notice"><strong>Organization administrator access</strong><p>This includes managing people, permissions and workspace settings, and granting access to any memory space.</p></div>}
            {permissions.space_count > 0 ? <>
              <div className="ws-table-wrap ws-consent-spaces"><table className="ws-table"><thead><tr><th>Memory space</th><th>Permission</th></tr></thead><tbody>{permissions.spaces.map(space => <tr key={space.id}><td>{space.name}</td><td>{space.role}</td></tr>)}</tbody></table></div>
              {permissions.space_count > permissions.spaces.length && <p>Showing {permissions.spaces.length} of {permissions.space_count} accessible spaces.</p>}
            </> : <p>This account currently has no memory-space access.</p>}
            <p>New permissions granted to this account will also be available to this app. To give an app narrower access, use a separate account with only the permissions it needs.</p>
            <p>You can revoke this connection from <strong>Account & sessions</strong> at any time.</p>
            <div className="ws-setup-actions"><button type="button" className="ws-button ws-quiet" onClick={() => void cancel()} disabled={busy}>Cancel</button><button type="button" className="ws-button ws-primary" onClick={() => void approve()} disabled={busy}>{busy ? 'Connecting…' : 'Allow connection'}<ArrowRight size={16} /></button></div>
            <button type="button" className="ws-button ws-quiet ws-consent-switch" disabled={busy} onClick={() => { setReview(undefined); setPassword(''); setError('') }}>Use another account</button>
          </div>}
        </>}
      </section>
      <p className="ws-consent-footer">Sign-in stays with your workspace or company provider. The connected app receives revocable access.</p>
    </div>
  </main>
}
