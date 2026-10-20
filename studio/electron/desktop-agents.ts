import type { AgentInstall, AgentPreview, AgentRemove, AgentSetup, AgentSetupResult, AgentSetupStatus } from '../shared/desktop-agents.js'
import type { SourceCall } from './desktop-sources.js'

/** One reviewed settings mutation, with the same private controller for UI/agents. */
export class DesktopAgents {
  private work?: Promise<Record<string, unknown>>
  private reading?: Promise<AgentSetupStatus>
  private suspended = false
  private closed = false
  private controllers = new Set<AbortController>()
  private calls = new Set<Promise<Record<string, unknown>>>()
  private timer?: ReturnType<typeof setInterval>
  constructor(private call: SourceCall) {}
  start() {
    if (this.timer || this.closed) return
    const refresh = () => { if (!this.suspended && !this.busy) void this.status().catch(() => {}) }
    refresh(); this.timer = setInterval(refresh, 300000); this.timer.unref()
  }
  get busy(): boolean { return !!this.work || !!this.reading || !!this.controllers.size }
  private async invoke(request: Record<string, unknown>, signal?: AbortSignal) {
    if (this.suspended || this.closed) throw new Error('Wait for the app to finish updating or closing.')
    const abort = new AbortController(), cancel = () => abort.abort()
    signal?.addEventListener('abort', cancel, { once: true })
    if (signal?.aborted) cancel()
    this.controllers.add(abort)
    const work = this.call(request, abort.signal)
    this.calls.add(work)
    try { return await work }
    finally { this.calls.delete(work); this.controllers.delete(abort); signal?.removeEventListener('abort', cancel) }
  }
  async status(): Promise<AgentSetupStatus> {
    if (this.work) await this.work.catch(() => {})
    if (!this.reading) this.reading = this.invoke({ operation: 'status' }).then(value => value as AgentSetupStatus)
      .finally(() => { this.reading = undefined })
    return this.reading
  }
  async preview(setup: AgentSetup, signal?: AbortSignal): Promise<AgentPreview> {
    if (this.work) throw new Error('Wait for the current agent setup operation.')
    return await this.invoke({ operation: 'preview', setup }, signal) as AgentPreview
  }
  private async mutate(operation: 'install' | 'remove', input: AgentInstall | AgentRemove, signal?: AbortSignal): Promise<AgentSetupResult> {
    if (this.work) throw new Error('Wait for the current agent setup operation.')
    if (this.reading) await this.reading.catch(() => {})
    if (this.work) throw new Error('Wait for the current agent setup operation.')
    this.work = this.invoke({ ...input, operation }, signal)
    try { return await this.work as AgentSetupResult } finally { this.work = undefined }
  }
  install(input: AgentInstall, signal?: AbortSignal) { return this.mutate('install', input, signal) }
  remove(input: AgentRemove, signal?: AbortSignal) { return this.mutate('remove', input, signal) }
  pauseForUpdate(): boolean { if (this.busy) return false; this.suspended = true; return true }
  resumeAfterUpdate() { this.suspended = false }
  async close() {
    this.closed = true
    clearInterval(this.timer); this.timer = undefined
    for (const controller of this.controllers) controller.abort()
    await Promise.allSettled([...this.calls])
  }
}
