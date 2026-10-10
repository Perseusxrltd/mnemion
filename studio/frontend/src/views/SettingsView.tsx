import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Settings, Server, Database, Brain, CheckCircle, AlertCircle, Save, ExternalLink, Download, FolderOpen, RefreshCw, Copy } from 'lucide-react'
import { api } from '../api/client'
import type { ObsidianStatus, StudioConfig } from '../types'

function Section({ title, icon: Icon, children }: { title: string; icon: any; children: React.ReactNode }) {
  return (
    <div className="rounded-xl p-5 fade-in" style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
      <h2 className="flex items-center gap-2 text-sm font-semibold mb-4">
        <Icon size={14} className="text-accent" />
        {title}
      </h2>
      {children}
    </div>
  )
}

function Field({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  const [copied, setCopied] = useState(false)
  return (
    <div className="flex items-center justify-between py-2 border-b" style={{ borderColor: 'var(--border)' }}>
      <span className="text-xs text-muted">{label}</span>
      <div className="flex items-center gap-2">
        <span className={`text-xs ${mono ? 'font-mono' : ''} text-right max-w-xs truncate`}>{value || '-'}</span>
        {value && (
          <button onClick={() => { navigator.clipboard.writeText(value); setCopied(true); setTimeout(() => setCopied(false), 1200) }}
            className="text-faint hover:text-muted transition-colors">
            {copied ? <CheckCircle size={10} className="text-emerald-400" /> : <Copy size={10} />}
          </button>
        )}
      </div>
    </div>
  )
}

export default function SettingsView() {
  const qc = useQueryClient()
  const { data: config, isLoading } = useQuery<StudioConfig>({
    queryKey: ['config'],
    queryFn: api.config,
  })
  const { data: obsidianStatus } = useQuery<ObsidianStatus>({
    queryKey: ['obsidian-status'],
    queryFn: api.obsidianStatus,
  })

  const [llmBackend, setLlmBackend] = useState('')
  const [llmUrl, setLlmUrl] = useState('')
  const [llmModel, setLlmModel] = useState('')
  const [llmKey, setLlmKey] = useState('')
  const [saved, setSaved] = useState(false)
  const [hydrated, setHydrated] = useState(false)
  const [backendPort, setBackendPort] = useState(7891)

  // Populate once config loads (don't clobber user edits)
  useEffect(() => {
    if (config && !hydrated) {
      setLlmBackend(config.llm?.backend ?? 'none')
      setLlmUrl(config.llm?.url ?? '')
      setLlmModel(config.llm?.model ?? '')
      setHydrated(true)
    }
  }, [config, hydrated])

  useEffect(() => {
    if (typeof window === 'undefined' || window.location.protocol !== 'file:') return

    let cancelled = false
    window.mnemion?.backendPort?.()
      .then(port => {
        if (!cancelled && Number.isInteger(port)) setBackendPort(port)
      })
      .catch(() => {
        if (!cancelled) setBackendPort(7891)
      })

    return () => { cancelled = true }
  }, [])

  const saveMut = useMutation({
    mutationFn: () => api.updateLLM({ backend: llmBackend, url: llmUrl, model: llmModel, api_key: llmKey || undefined }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['config'] })
      setSaved(true)
      setLlmKey('')
      setTimeout(() => setSaved(false), 2000)
    },
  })
  const syncObsidianMut = useMutation({
    mutationFn: api.syncObsidian,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['obsidian-status'] }),
  })
  const setupObsidianMut = useMutation({
    mutationFn: async () => {
      await api.syncObsidian()
      return api.openObsidian()
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['obsidian-status'] }),
  })
  const downloadVaultMut = useMutation({
    mutationFn: () => api.downloadVault(),
  })

  if (isLoading) {
    return <div className="flex-1 flex items-center justify-center text-sm text-muted">Loading settings...</div>
  }

  const BACKENDS = [
    { value: 'none', label: 'Off - local search only' },
    { value: 'ollama', label: 'Ollama - local' },
    { value: 'lmstudio', label: 'LM Studio - local' },
    { value: 'vllm', label: 'vLLM - local server' },
    { value: 'openai', label: 'OpenAI - cloud' },
    { value: 'custom', label: 'Custom provider' },
  ]
  const diagnosticsUrl = typeof window !== 'undefined' && window.location.protocol === 'file:'
    ? `http://127.0.0.1:${backendPort}/api/docs`
    : '/api/docs'

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-4">
      <div className="fade-in">
        <h1 className="text-xl font-semibold tracking-tight">Settings</h1>
        <p className="text-sm text-muted mt-0.5">Local memory storage, optional AI help, and export settings.</p>
      </div>

      <Section title="Local Memory Store" icon={Database}>
        <Field label="Path" value={config?.anaktoron_path ?? ''} mono />
        <Field label="Collection" value={config?.collection_name ?? ''} mono />
        <Field label="Memory areas" value={(config?.topic_wings ?? []).join(', ')} />
      </Section>

      <Section title="AI Helper" icon={Brain}>
        <p className="text-xs text-muted mb-4">
          Optional AI help improves duplicate checks, topic suggestions, and relationship extraction.
          Choose a local provider to keep everything on this computer.
        </p>

        <div className="space-y-3">
          <div>
            <label className="text-xs text-muted block mb-1.5">Provider</label>
            <select
              value={llmBackend}
              onChange={e => setLlmBackend(e.target.value)}
              className="w-full px-3 py-2 rounded-lg text-sm border outline-none focus:border-accent transition-colors"
              style={{ background: 'var(--raised)', borderColor: 'var(--border)', color: 'var(--text)' }}
            >
              {BACKENDS.map(b => <option key={b.value} value={b.value}>{b.label}</option>)}
            </select>
          </div>

          {llmBackend !== 'none' && (
            <>
              <div>
                <label className="text-xs text-muted block mb-1.5">Service URL</label>
                <input
                  value={llmUrl}
                  onChange={e => setLlmUrl(e.target.value)}
                  placeholder="http://localhost:8000"
                  className="w-full px-3 py-2 rounded-lg text-sm border outline-none focus:border-accent transition-colors font-mono"
                  style={{ background: 'var(--raised)', borderColor: 'var(--border)', color: 'var(--text)' }}
                />
              </div>
              <div>
                <label className="text-xs text-muted block mb-1.5">Model</label>
                <input
                  value={llmModel}
                  onChange={e => setLlmModel(e.target.value)}
                  placeholder="model name or path"
                  className="w-full px-3 py-2 rounded-lg text-sm border outline-none focus:border-accent transition-colors font-mono"
                  style={{ background: 'var(--raised)', borderColor: 'var(--border)', color: 'var(--text)' }}
                />
              </div>
              {(llmBackend === 'openai' || llmBackend === 'custom') && (
                <div>
                  <label className="text-xs text-muted block mb-1.5">API Key</label>
                  <input
                    value={llmKey}
                    onChange={e => setLlmKey(e.target.value)}
                    type="password"
                    placeholder="sk-..."
                    className="w-full px-3 py-2 rounded-lg text-sm border outline-none focus:border-accent transition-colors font-mono"
                    style={{ background: 'var(--raised)', borderColor: 'var(--border)', color: 'var(--text)' }}
                  />
                </div>
              )}
            </>
          )}

          <button
            onClick={() => saveMut.mutate()}
            disabled={saveMut.isPending}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
            style={{ background: 'var(--accent)', color: 'white' }}
          >
            {saved ? <CheckCircle size={14} className="text-emerald-300" /> : <Save size={14} />}
            {saved ? 'Saved!' : saveMut.isPending ? 'Saving...' : 'Save AI settings'}
          </button>

          {saveMut.isError && (
            <div className="flex items-center gap-1.5 text-xs text-red-400">
              <AlertCircle size={12} /> Failed to save
            </div>
          )}
        </div>
      </Section>

      <Section title="App Health" icon={Server}>
        <div className="space-y-2 text-xs text-muted">
          <Field label="Memory service port" value={String(backendPort)} mono />
          <Field
            label="App window"
            value={typeof window !== 'undefined' ? window.location.host : ''}
            mono
          />
          <details className="pt-2">
            <summary className="cursor-pointer text-faint hover:text-muted">Advanced diagnostics</summary>
            <a
              href={diagnosticsUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-2 flex items-center gap-1.5 text-accent hover:underline"
            >
              <ExternalLink size={11} /> Open service diagnostics
            </a>
          </details>
        </div>
      </Section>

      <Section title="Markdown Backup" icon={FolderOpen}>
        <div className="space-y-2 mb-4">
          <Field label="Vault" value={obsidianStatus?.vault_path ?? ''} mono />
          <Field label="Registered" value={obsidianStatus?.registered ? 'yes' : 'no'} />
          <Field label="Markdown files" value={String(obsidianStatus?.file_count ?? 0)} />
          <Field label="Memories" value={String(obsidianStatus?.drawer_count ?? 0)} />
          <Field label="Last sync" value={obsidianStatus?.last_sync ?? 'never'} mono />
        </div>
        <div className="flex flex-wrap gap-3">
          <button
            onClick={() => setupObsidianMut.mutate()}
            disabled={setupObsidianMut.isPending}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
            style={{ background: 'var(--accent)', color: 'white' }}
          >
            <ExternalLink size={14} />
            {setupObsidianMut.isPending ? 'Opening...' : 'Create, Refresh, and Open'}
          </button>
          <button
            onClick={() => syncObsidianMut.mutate()}
            disabled={syncObsidianMut.isPending}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium border transition-colors disabled:opacity-50"
            style={{ background: 'var(--raised)', borderColor: 'var(--border)', color: 'var(--text)' }}
          >
            <RefreshCw size={14} />
            {syncObsidianMut.isPending ? 'Refreshing...' : 'Refresh Only'}
          </button>
          <button
            onClick={() => downloadVaultMut.mutate()}
            disabled={downloadVaultMut.isPending}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium border transition-colors"
            style={{ background: 'var(--raised)', borderColor: 'var(--border)', color: 'var(--text)' }}
          >
            <Download size={14} /> {downloadVaultMut.isPending ? 'Preparing ZIP...' : 'Download ZIP'}
          </button>
        </div>
        {(setupObsidianMut.isError || syncObsidianMut.isError || downloadVaultMut.isError) && (
          <div className="mt-3 flex items-center gap-1.5 text-xs text-red-400">
            <AlertCircle size={12} /> Backup action failed
          </div>
        )}
        {obsidianStatus?.config_error && (
          <div className="mt-3 flex items-center gap-1.5 text-xs text-amber-400">
            <AlertCircle size={12} /> {obsidianStatus.config_error}
          </div>
        )}
      </Section>

      <Section title="Automatic Capture Hook" icon={Settings}>
        <p className="text-xs text-muted mb-3">
          Advanced: install the save hook to capture memories automatically from compatible AI apps.
        </p>
        <pre className="bg-raised rounded-lg p-3 text-[11px] font-mono text-white/70 overflow-x-auto">{`# In your CLAUDE.md hooks config:
[hooks.post_tool_use]
command = "python ~/.mnemion/hooks/mnemion_save_hook.py"`}</pre>
      </Section>
    </div>
  )
}
