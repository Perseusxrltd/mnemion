import { useState, useEffect, useRef } from 'react'
import { Brain, Save, Plus, Trash2, HelpCircle, FileText, Check, AlertCircle } from 'lucide-react'
import { api } from '../api/client'
import type { CoreMemory } from '../types'

// Simple Markdown rendering helper for core memory previews
function renderSimpleMarkdown(md: string): string {
  if (!md) return '<p class="text-faint italic">No content. Start typing to see preview...</p>'
  
  let html = md
    // Escape HTML tags to prevent XSS in preview
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    
  // Headers
  html = html.replace(/^### (.*$)/gim, '<h3 class="text-sm font-semibold mt-3 mb-1 text-white">$1</h3>')
  html = html.replace(/^## (.*$)/gim, '<h2 class="text-base font-semibold mt-4 mb-2 text-white border-b border-border pb-1">$1</h2>')
  html = html.replace(/^# (.*$)/gim, '<h1 class="text-lg font-bold mt-5 mb-3 text-white border-b border-border pb-2">$1</h1>')
  
  // Bold
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong class="font-semibold text-white">$1</strong>')
  html = html.replace(/\*(.*?)\*/g, '<em class="italic">$1</em>')
  
  // Bullet lists
  html = html.replace(/^\s*-\s+(.*$)/gim, '<li class="list-disc ml-5 my-0.5 text-muted">$1</li>')
  html = html.replace(/^\s*\*\s+(.*$)/gim, '<li class="list-disc ml-5 my-0.5 text-muted">$1</li>')
  
  // Wrap list items
  html = html.replace(/(<li>.*<\/li>)/gim, '<ul class="my-2">$1</ul>')
  // Clean up adjacent list wrappers
  html = html.replace(/<\/ul>\s*<ul class="my-2">/g, '')

  // Inline Code
  html = html.replace(/`(.*?)`/g, '<code class="px-1.5 py-0.5 rounded text-[11px] font-mono bg-raised border text-purple-300 border-border">$1</code>')
  
  // Blocks
  html = html.replace(/^\s*>\s+(.*$)/gim, '<blockquote class="border-l-2 pl-3 my-2 text-faint italic border-purple-500 bg-raised py-1 rounded-r">$1</blockquote>')
  
  // Paragraphs
  html = html.replace(/\n\n/g, '</p><p class="my-2 text-muted leading-relaxed">')
  html = '<p class="my-2 text-muted leading-relaxed">' + html + '</p>'
  
  // Clean empty paragraphs
  html = html.replace(/<p class="[^"]*"><\/p>/g, '')
  
  return html
}

export default function CoreMemoryView() {
  const [memories, setMemories] = useState<CoreMemory[]>([])
  const [activeKey, setActiveKey] = useState<string>('default')
  const [content, setContent] = useState<string>('')
  const [originalContent, setOriginalContent] = useState<string>('')
  const [searchQuery, setSearchQuery] = useState<string>('')
  
  // UI States
  const [isCreating, setIsCreating] = useState<boolean>(false)
  const [newKey, setNewKey] = useState<string>('')
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [saveError, setSaveError] = useState<string>('')
  const [isLoading, setIsLoading] = useState<boolean>(true)
  const [showHelp, setShowHelp] = useState<boolean>(true)

  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    fetchMemories()
  }, [])

  useEffect(() => {
    // When activeKey changes, load its content
    const activeMem = memories.find(m => m.key === activeKey)
    if (activeMem) {
      setContent(activeMem.content)
      setOriginalContent(activeMem.content)
    } else if (activeKey === 'default' && memories.length === 0) {
      // If we don't have default, mock empty
      setContent('')
      setOriginalContent('')
    }
  }, [activeKey, memories])

  // Ctrl+S key listener for saving
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault()
        handleSave()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [content, activeKey, originalContent])

  async function fetchMemories() {
    setIsLoading(true)
    try {
      const data = await api.getCoreMemories()
      setMemories(data)
      
      // If we have memories and activeKey is default, make sure we stay on it
      // or pick the first one if default isn't there
      if (data.length > 0) {
        if (!data.some(m => m.key === activeKey)) {
          setActiveKey(data[0].key)
        }
      } else {
        // Create default memory if none exists
        await api.updateCoreMemory('default', '# Core Working Memory\n\n- Milestone: Initial project audit completed.\n- State: Running locally.\n- Rules: Prioritize local-first databases.')
        const refreshed = await api.getCoreMemories()
        setMemories(refreshed)
        setActiveKey('default')
      }
    } catch (e: any) {
      console.error(e)
    } finally {
      setIsLoading(false)
    }
  }

  async function handleSave() {
    if (content === originalContent && saveStatus !== 'error') return
    setSaveStatus('saving')
    setSaveError('')
    try {
      await api.updateCoreMemory(activeKey, content)
      setSaveStatus('saved')
      setOriginalContent(content)
      
      // Update local state list
      setMemories(prev =>
        prev.map(m => (m.key === activeKey ? { ...m, content } : m))
      )
      
      setTimeout(() => setSaveStatus('idle'), 2000)
    } catch (e: any) {
      setSaveStatus('error')
      setSaveError(e.message || 'Failed to save core memory block.')
    }
  }

  async function handleCreateBlock(e: React.FormEvent) {
    e.preventDefault()
    const cleanKey = newKey.trim().toLowerCase().replace(/[^a-z0-9_-]/g, '')
    if (!cleanKey) return
    
    if (memories.some(m => m.key === cleanKey)) {
      alert('A core memory block with that key already exists!')
      return
    }

    try {
      const template = `# Core Memory: ${cleanKey}\n\n- Status: Active\n- Current task: \n- Core requirements:\n- Notes:\n`
      await api.updateCoreMemory(cleanKey, template)
      
      // Refresh list
      const updated = await api.getCoreMemories()
      setMemories(updated)
      setActiveKey(cleanKey)
      setIsCreating(false)
      setNewKey('')
    } catch (e: any) {
      alert('Failed to create block: ' + e.message)
    }
  }

  const filteredMemories = memories.filter(m =>
    m.key.toLowerCase().includes(searchQuery.toLowerCase())
  )

  const isDirty = content !== originalContent

  return (
    <div className="flex-1 flex overflow-hidden">
      {/* Left Sidebar - Key List */}
      <div
        className="w-64 flex-shrink-0 flex flex-col border-r overflow-hidden"
        style={{
          background: 'var(--background-secondary)',
          borderColor: 'var(--background-modifier-border)',
        }}
      >
        <div className="p-3 border-b flex items-center justify-between" style={{ borderColor: 'var(--background-modifier-border)' }}>
          <div className="flex items-center gap-2">
            <Brain size={14} className="text-purple-400" />
            <span className="text-xs font-semibold uppercase tracking-wider text-muted">Core Blocks</span>
          </div>
          <button
            onClick={() => setIsCreating(true)}
            className="p-1 rounded hover-row transition-colors text-muted hover:text-white"
            title="Create new core memory block"
          >
            <Plus size={14} />
          </button>
        </div>

        {/* Search */}
        <div className="p-2 border-b" style={{ borderColor: 'var(--background-modifier-border)' }}>
          <input
            type="text"
            placeholder="Search keys..."
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            className="w-full text-xs px-2.5 py-1.5 rounded-lg border focus:outline-none"
            style={{
              background: 'var(--surface)',
              borderColor: 'var(--background-modifier-border)',
              color: 'var(--text-normal)',
            }}
          />
        </div>

        {/* Create Form inline modal */}
        {isCreating && (
          <form onSubmit={handleCreateBlock} className="p-3 border-b space-y-2 bg-raised" style={{ borderColor: 'var(--background-modifier-border)' }}>
            <div className="text-[11px] font-medium text-muted">New Block Key:</div>
            <input
              type="text"
              autoFocus
              placeholder="e.g. project-x"
              value={newKey}
              onChange={e => setNewKey(e.target.value)}
              className="w-full text-xs px-2 py-1 rounded border focus:outline-none focus:border-purple-500 font-mono"
              style={{
                background: 'var(--surface)',
                borderColor: 'var(--background-modifier-border)',
                color: 'var(--text-normal)',
              }}
            />
            <div className="flex gap-1.5 justify-end">
              <button
                type="button"
                onClick={() => setIsCreating(false)}
                className="text-[10px] px-2 py-1 rounded hover-row text-muted"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="text-[10px] px-2 py-1 rounded bg-purple-600 text-white font-medium hover:bg-purple-500"
              >
                Create
              </button>
            </div>
          </form>
        )}

        {/* List of keys */}
        <div className="flex-1 overflow-y-auto p-1.5 space-y-0.5">
          {isLoading ? (
            <div className="text-xs text-center text-faint p-4">Loading keys...</div>
          ) : filteredMemories.length === 0 ? (
            <div className="text-xs text-center text-faint p-4">No keys found</div>
          ) : (
            filteredMemories.map(m => {
              const active = m.key === activeKey
              return (
                <button
                  key={m.key}
                  onClick={() => {
                    if (isDirty) {
                      if (!confirm('You have unsaved changes in the current block. Discard them?')) return
                    }
                    setActiveKey(m.key)
                  }}
                  className={`flex items-center gap-2 w-full px-2.5 py-2 rounded-lg text-left text-xs transition-colors ${
                    active ? 'active text-white' : 'text-muted hover-row'
                  }`}
                  style={active ? { background: 'rgba(127,109,242,0.15)', borderLeft: '2px solid var(--interactive-accent)' } : {}}
                >
                  <FileText size={12} className={active ? 'text-purple-400' : 'text-faint'} />
                  <span className="flex-1 truncate font-mono">{m.key}</span>
                  {m.key === 'default' && (
                    <span className="text-[9px] px-1 py-0.5 rounded opacity-50 bg-raised border border-border">
                      main
                    </span>
                  )}
                </button>
              )
            })
          )}
        </div>

        {/* Info footer */}
        <div className="p-3 border-t text-[11px] text-faint bg-raised" style={{ borderColor: 'var(--background-modifier-border)' }}>
          Always injected into connected MCP agents' system prompts.
        </div>
      </div>

      {/* Main Workspace */}
      <div className="flex-1 flex flex-col overflow-hidden bg-surface">
        {/* Workspace Header */}
        <div
          className="px-6 py-4 border-b flex items-center justify-between"
          style={{ borderColor: 'var(--background-modifier-border)', background: 'var(--background-secondary)' }}
        >
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-sm font-semibold font-mono text-white">{activeKey}</h1>
              <span className="text-[10px] text-faint">Core Memory Block</span>
            </div>
            <p className="text-[11px] text-muted mt-0.5">
              Agents access this block live during sessions to align on goals and context.
            </p>
          </div>

          <div className="flex items-center gap-2">
            {isDirty && (
              <span className="text-[10px] text-yellow-500 font-medium px-2 py-0.5 rounded bg-yellow-500/10 border border-yellow-500/20">
                Unsaved Changes
              </span>
            )}
            
            {/* Status indicator */}
            {saveStatus === 'saving' && (
              <span className="text-[11px] text-muted flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-purple-500 animate-pulse" /> Saving...
              </span>
            )}
            {saveStatus === 'saved' && (
              <span className="text-[11px] text-green-400 flex items-center gap-1">
                <Check size={12} /> Saved
              </span>
            )}
            {saveStatus === 'error' && (
              <span className="text-[11px] text-red-400 flex items-center gap-1" title={saveError}>
                <AlertCircle size={12} /> Save Error
              </span>
            )}

            <button
              onClick={handleSave}
              disabled={!isDirty || saveStatus === 'saving'}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                isDirty
                  ? 'bg-purple-600 hover:bg-purple-500 text-white shadow-lg shadow-purple-600/15'
                  : 'bg-raised text-faint cursor-not-allowed border border-border'
              }`}
            >
              <Save size={12} />
              Save <span className="opacity-50 text-[10px] font-normal font-mono ml-0.5">Ctrl+S</span>
            </button>

            <button
              onClick={() => setShowHelp(h => !h)}
              className={`p-1.5 rounded-lg border transition-colors ${
                showHelp ? 'bg-purple-500/10 text-purple-400 border-purple-500/20' : 'bg-raised text-muted border-border hover-row'
              }`}
              title="Toggle explanation panel"
            >
              <HelpCircle size={14} />
            </button>
          </div>
        </div>

        {/* Explain panel */}
        {showHelp && (
          <div className="px-6 py-4 border-b text-xs space-y-2 bg-purple-500/5 border-purple-500/10 text-muted transition-all">
            <div className="font-semibold text-purple-300 flex items-center gap-1.5">
              💡 What is Core Working Memory?
            </div>
            <p className="leading-relaxed">
              Inspired by Letta and MemGPT, Mnemion's Core Working Memory provides a persistent scratchpad for agents. Instead of passive context lookup (RAG), this memory block is **permanently injected into the agent's context window**.
            </p>
            <div className="grid grid-cols-2 gap-4 pt-1 font-mono text-[11px]">
              <div className="p-2.5 rounded bg-raised border">
                <span className="text-purple-300"># Retrieval Tool</span><br />
                mnemion_get_core_memory(key="{activeKey}")
              </div>
              <div className="p-2.5 rounded bg-raised border">
                <span className="text-purple-300"># Update Tool</span><br />
                mnemion_update_core_memory(key="{activeKey}", content="...")
              </div>
            </div>
            <p className="text-[10px] text-faint pt-1">
              Perfect for storing: current workspace guidelines, sprint goals, persistent persona parameters, and structural directories.
            </p>
          </div>
        )}

        {/* Editor Workspace: Side by Side */}
        <div className="flex-1 flex overflow-hidden">
          {/* Markdown Editor */}
          <div className="flex-1 flex flex-col h-full border-r border-border overflow-hidden">
            <div className="px-3 py-1.5 bg-raised text-[10px] font-semibold text-muted uppercase tracking-wider border-b border-border">
              Editor (Markdown)
            </div>
            <textarea
              ref={textareaRef}
              value={content}
              onChange={e => setContent(e.target.value)}
              placeholder="# Project Working Memory&#10;&#10;- Current Goal: ...&#10;- Stack: React + FastAPI&#10;- Decisions: ..."
              className="flex-1 w-full p-4 font-mono text-xs leading-relaxed resize-none focus:outline-none bg-surface text-normal scrollbar"
              style={{ caretColor: 'var(--interactive-accent)' }}
            />
            <div className="px-4 py-2 bg-raised border-t text-[10px] text-muted flex justify-between">
              <span>{content.split(/\s+/).filter(Boolean).length} words</span>
              <span>{content.length} characters</span>
            </div>
          </div>

          {/* HTML Render Preview */}
          <div className="flex-1 flex flex-col h-full overflow-hidden bg-raised">
            <div className="px-3 py-1.5 text-[10px] font-semibold text-muted uppercase tracking-wider border-b border-border">
              Live Preview
            </div>
            <div
              className="flex-1 p-5 overflow-y-auto scrollbar select-text selection:bg-purple-500/20"
              dangerouslySetInnerHTML={{ __html: renderSimpleMarkdown(content) }}
            />
          </div>
        </div>
      </div>
    </div>
  )
}
