import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Settings, Server, Database, Brain, CheckCircle, AlertCircle, Save, ExternalLink, Download, FolderOpen } from 'lucide-react'
import { api } from '../api/client'
import type { StudioConfig } from '../types'

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
        <span className={`text-xs ${mono ? 'font-mono' : ''} text-right max-w-xs truncate`}>{value || '—'}</span>
        {value && (
          <button onClick={() => { navigator.clipboard.writeText(value); setCopied(true); setTimeout(() => setCopied(false), 1200) }}
            className="text-faint hover:text-muted transition-colors">
            {copied ? <CheckCircle size={10} className="text-emerald-400" /> : <span className="text-[9px]">⧉</span>}
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

  const [llmBackend, setLlmBackend] = useState('')
  const [llmUrl, setLlmUrl] = useState('')
  const [llmModel, setLlmModel] = useState('')
  const [llmKey, setLlmKey] = useState('')
  const [saved, setSaved] = useState(false)
  const [hydrated, setHydrated] = useState(false)

  // Populate once config loads (don't clobber user edits)
  useEffect(() => {
    if (config && !hydrated) {
      setLlmBackend(config.llm?.backend ?? 'none')
      setLlmUrl(config.llm?.url ?? '')
      setLlmModel(config.llm?.model ?? '')
      setHydrated(true)
    }
  }, [config, hydrated])

  const saveMut = useMutation({
    mutationFn: () => api.updateLLM({ backend: llmBackend, url: llmUrl, model: llmModel, api_key: llmKey }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['config'] })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    },
  })

  if (isLoading) {
    return <div className="flex-1 flex items-center justify-center text-sm text-muted">Loading config…</div>
  }

  const BACKENDS = ['none', 'ollama', 'lmstudio', 'vllm', 'openai', 'custom']

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-4">
      <div className="fade-in">
        <h1 className="text-xl font-semibold tracking-tight">Settings</h1>
        <p className="text-sm text-muted mt-0.5">Anaktoron configuration and LLM backend.</p>
      </div>

      <Section title="Anaktoron" icon={Database}>
        <Field label="Path" value={config?.anaktoron_path ?? ''} mono />
        <Field label="Collection" value={config?.collection_name ?? ''} mono />
        <Field label="Topic wings" value={(config?.topic_wings ?? []).join(', ')} />
      </Section>

      <Section title="LLM Backend" icon={Brain}>
        <p className="text-xs text-muted mb-4">
          The LLM backend powers contradiction detection, room classification, and KG extraction.
          It runs locally — no data leaves your machine.
        </p>

        <div className="space-y-3">
          <div>
            <label className="text-xs text-muted block mb-1.5">Backend</label>
            <select
              value={llmBackend}
              onChange={e => setLlmBackend(e.target.value)}
              className="w-full px-3 py-2 rounded-lg text-sm border outline-none focus:border-accent transition-colors"
              style={{ background: 'var(--raised)', borderColor: 'var(--border)', color: 'var(--text)' }}
            >
              {BACKENDS.map(b => <option key={b} value={b}>{b}</option>)}
            </select>
          </div>

          {llmBackend !== 'none' && (
            <>
              <div>
                <label className="text-xs text-muted block mb-1.5">URL</label>
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
                    placeholder="sk-…"
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
            {saved ? 'Saved!' : saveMut.isPending ? 'Saving…' : 'Save LLM config'}
          </button>

          {saveMut.isError && (
            <div className="flex items-center gap-1.5 text-xs text-red-400">
              <AlertCircle size={12} /> Failed to save
            </div>
          )}
        </div>
      </Section>

      <Section title="Studio" icon={Server}>
        <div className="space-y-2 text-xs text-muted">
          <Field label="Backend port" value="7891" mono />
          <Field
            label="Frontend"
            value={typeof window !== 'undefined' ? window.location.host : ''}
            mono
          />
          <div className="pt-2">
            <a
              href="/api/docs"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 text-accent hover:underline"
            >
              <ExternalLink size={11} /> OpenAPI docs
            </a>
          </div>
        </div>
      </Section>

      <Section title="Obsidian Vault Export" icon={FolderOpen}>
        <p className="text-xs text-muted mb-4">
          Export your entire Anaktoron as Obsidian-compatible Markdown files with YAML frontmatter.
          Open the resulting folder as a vault in Obsidian to browse your memories visually.
        </p>
        <div className="flex flex-wrap gap-3">
          <a
            href={api.exportVaultUrl()}
            download
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors"
            style={{ background: 'var(--accent)', color: 'white' }}
          >
            <Download size={14} /> Export full vault
          </a>
          <div className="text-xs text-muted self-center">
            Downloads as <code className="bg-raised px-1 rounded">mnemion_vault.zip</code>
          </div>
        </div>
        <div className="mt-3 text-xs text-faint">
          Each drawer becomes a <code className="bg-raised px-1 rounded">.md</code> file with YAML frontmatter
          (wing, room, agent, trust_status, confidence).
          Wikilinks <code className="bg-raised px-1 rounded">[[entity]]</code> from Knowledge Graph entries are preserved.
        </div>
      </Section>

      <Section title="MCP Hook" icon={Settings}>
        <p className="text-xs text-muted mb-3">
          Install the save hook to capture memories automatically when an agent calls <code className="bg-raised px-1 rounded text-accent/80">mnemion_add_drawer</code>.
        </p>
        <pre className="bg-raised rounded-lg p-3 text-[11px] font-mono text-white/70 overflow-x-auto">{`# In your CLAUDE.md hooks config:
[hooks.post_tool_use]
command = "python ~/.mnemion/hooks/mnemion_save_hook.py"`}</pre>
      </Section>
    </div>
  )
}
