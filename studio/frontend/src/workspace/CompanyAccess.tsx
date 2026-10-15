import { useState, type FormEvent } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Building2, RefreshCw } from 'lucide-react'
import { MnemionError } from '@mnemion/client'
import type { Connection } from './connection-types'

const date = (value: string | null) => value ? new Date(value).toLocaleString() : 'Not yet'

export default function CompanyAccess({ connection, people, disconnect }: {
  connection: Connection
  people: { id: string; name: string }[]
  disconnect: () => void
}) {
  const { client, me } = connection, cache = useQueryClient()
  const configuration = useQuery({ queryKey: ['company-configuration', me.tenant_id],
    queryFn: () => client.companyConfiguration(me.tenant_id), retry: false })
  const links = useQuery({ queryKey: ['company-links'], queryFn: () => client.companyLinks(),
    enabled: configuration.isSuccess, retry: false })
  const [person, setPerson] = useState(''), [provider, setProvider] = useState(''), [subject, setSubject] = useState('')
  const [pending, setPending] = useState<string>(), [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(), [notice, setNotice] = useState('')
  const providers = configuration.data?.providers ?? []
  const selected = links.data?.items.find(link => link.id === pending)
  const personName = (id: string) => id === me.principal_id ? me.name : people.find(person => person.id === id)?.name ?? id
  async function run(action: () => Promise<void | false>) {
    setBusy(true); setError(undefined); setNotice('')
    try {
      if (await action() !== false) await Promise.all([
        cache.invalidateQueries({ queryKey: ['company-links'] }), cache.invalidateQueries({ queryKey: ['device-sessions'] }),
      ])
    } catch (error) { setError(error) } finally { setBusy(false) }
  }
  function link(event: FormEvent) {
    event.preventDefault()
    void run(async () => {
      await client.linkCompanyIdentity({ principal_id: person, provider_id: provider, subject })
      setPerson(''); setProvider(''); setSubject('')
      setNotice('Company identity linked. The person can use the workspace sign-in link with their existing permissions.')
    })
  }
  const failure = error || configuration.error || links.error
  if (configuration.error instanceof MnemionError && configuration.error.status === 404) return null
  return <section className="ws-card" aria-label="Company access">
    <div className="ws-section-title"><h2><Building2 size={19} />Company access</h2>
      <button type="button" className="ws-button ws-quiet" disabled={busy || configuration.isFetching || links.isFetching}
        onClick={() => { void configuration.refetch(); if (configuration.isSuccess) void links.refetch() }}><RefreshCw size={14} />Refresh</button></div>
    <p>Use your company account to sign in. Your workspace permissions are assigned by a Mnemion administrator.</p>
    {failure && <div className="ws-notice ws-error" role="alert">{failure instanceof Error ? failure.message : 'Company access could not be loaded.'}</div>}
    {notice && <p className="ws-notice" role="status">{notice}</p>}
    {configuration.isSuccess && (providers.length ? <ul>{providers.map(provider => <li key={provider.id}>
      <strong>{provider.name}</strong> · Sign in again after {provider.session_seconds % 3600 === 0 ? `${provider.session_seconds / 3600} hours` : `${provider.session_seconds / 60} minutes`}
      {me.administrator && <><br /><small>{provider.issuer}</small></>}
    </li>)}</ul> : <p>No company sign-in provider is enabled for this workspace. {me.administrator && 'The host operator can connect your identity provider using the company sign-in guide in Help.'}</p>)}
    {links.data && <><div className="ws-table-wrap"><table className="ws-table"><thead><tr><th>Person</th><th>Company account</th><th>Last sign-in</th><th>Access</th></tr></thead><tbody>
      {links.data.items.map(link => <tr key={link.id}><td>{personName(link.principal_id)}</td><td>{providers.find(provider => provider.id === link.provider_id)?.name ?? link.provider_id}
        <details><summary>Identity details</summary><small>{link.issuer}</small><code>{link.subject}</code></details></td>
        <td>{date(link.last_authenticated_at)}</td><td>{link.revoked_at ? 'Revoked' : <button type="button" className="ws-button ws-quiet" disabled={busy} onClick={() => setPending(link.id)}>Revoke company access</button>}</td></tr>)}
    </tbody></table></div>
      {!links.data.items.length && <p>No linked company accounts to show.</p>}
      {links.data.items.length >= 1000 && <p>Showing the first 1,000 linked accounts returned by the server.</p>}
    </>}
    {selected && <div className="ws-notice" role="group" aria-label="Confirm company access revocation">
      <p>Revoke company sign-in for <strong>{personName(selected.principal_id)}</strong>? Sessions using this linked identity end immediately. The administrator must explicitly link it again to restore company sign-in.</p>
      <button type="button" className="ws-button" disabled={busy} onClick={() => void run(async () => {
        await client.revokeCompanyIdentity(selected.id); setPending(undefined)
        setNotice('Company access revoked. Independent password logins and API keys remain available.')
        if (selected.principal_id === me.principal_id && connection.authentication === 'company') {
          try { await client.me() } catch (error) { if (error instanceof MnemionError && error.status === 401) { disconnect(); return false }; throw error }
        }
      })}>Revoke access</button><button type="button" className="ws-button ws-quiet" disabled={busy} onClick={() => setPending(undefined)}>Keep access</button>
    </div>}
    {me.administrator && providers.length > 0 && <>
      <p>For a new person, assign their space access and create a first-login invitation below. They can accept it with their company account.</p>
      <details><summary>Link an existing company identity</summary><form className="ws-form" onSubmit={link}>
        <p>Use the exact, permanent subject identifier from your identity provider. An email address or domain does not establish identity or grant access.</p>
        <label className="ws-field"><span>Person</span><select value={person} onChange={event => setPerson(event.target.value)} required disabled={busy}><option value="">Choose a person</option>{people.map(person => <option key={person.id} value={person.id}>{person.name}</option>)}</select></label>
        <label className="ws-field"><span>Company provider</span><select value={provider} onChange={event => setProvider(event.target.value)} required disabled={busy}><option value="">Choose a provider</option>{providers.map(provider => <option key={provider.id} value={provider.id}>{provider.name}</option>)}</select></label>
        <label className="ws-field"><span>Permanent subject identifier</span><input value={subject} onChange={event => setSubject(event.target.value)} required maxLength={255} autoComplete="off" autoCapitalize="none" spellCheck={false} disabled={busy} /></label>
        <small>Linking grants this identity the selected person’s current access. Relinking an existing identity ends its previous sessions; it cannot be reassigned to another person.</small>
        <button className="ws-button ws-primary" disabled={busy || !person || !provider || !subject}>Link company identity</button>
      </form></details>
    </>}
    <p><small>Revoke a linked account here, or disable the person in Team, to end Mnemion access immediately. Upstream company account changes take effect at the next sign-in; already issued sessions have the duration shown above.</small></p>
    <Link className="ws-link" to="/workspace/help?doc=docs%2Fservice%2Fcompany-sign-in.md">Company sign-in guide</Link>
  </section>
}
