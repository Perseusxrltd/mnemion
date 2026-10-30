/** Installed 128-cycle resource workload. Delivery stays a separate two-launch check. */
import type { BrowserWindow } from 'electron'
import { app } from 'electron'
import { renameSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { canonicalMemoryCycles, canonicalRemainingBatches, canonicalTerminalMarker, resourceProgress } from './canonical-memory-cycles.mjs'
import { settleInstalledTelemetryDelivery } from './service-bridge.js'

const CHECKPOINTS = [
  'before_workspace_connect',
  'workspace_connected',
  'first_memory_cycle_and_delivery',
  '8_memory_cycles',
  '16_memory_cycles',
  '32_memory_cycles',
  '64_memory_cycles',
  '96_memory_cycles',
  '128_memory_cycles',
] as const

const PROBE_ENTRY = './assets/packaged-memory-probe.js'

let persistedPhase: string | null = null

function marker(phase: string, completed?: number, known = true): void {
  const root = process.env.MNEMION_STUDIO_USER_DATA
  if (!root) throw new Error('Disposable profile required')
  const terminal = phase === 'finished' || phase === 'closed' || phase === 'failed'
  const body = terminal
    ? { at_ms: Date.now(), ...canonicalTerminalMarker(phase, completed, known) }
    : known === false
      ? { at_ms: Date.now(), phase, completed, completed_known: false }
      : { at_ms: Date.now(), phase }
  const file = join(root, 'monitor.json')
  writeFileSync(`${file}.tmp`, JSON.stringify(body))
  renameSync(`${file}.tmp`, file)
  if (!terminal) persistedPhase = phase
}

function loopbackOrigin(value: unknown): string {
  if (typeof value !== 'string' || value.length > 128) throw new Error('Telemetry resource fixture refused a non-loopback destination')
  let url: URL
  try { url = new URL(value) } catch { throw new Error('Telemetry resource fixture refused a non-loopback destination') }
  const port = Number(url.port)
  if (url.protocol !== 'http:' || (url.hostname !== '127.0.0.1' && url.hostname !== 'localhost') ||
      url.username || url.password || url.search || url.hash ||
      (url.pathname !== '/' && url.pathname !== '') ||
      !Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error('Telemetry resource fixture refused a non-loopback destination')
  }
  return url.origin
}

function resourceConfig(config: Record<string, unknown>) {
  const keys = Object.keys(config).sort().join()
  if (keys !== 'condition,credential,endpoint,label,package_condition,package_sha256,phase,probe_entry,replicate,source,spaceId' ||
      config.phase !== 'telemetry-resource') throw new Error('Invalid telemetry resource configuration')
  const condition = config.condition
  const packageCondition = config.package_condition
  if ((condition !== 'unavailable' && condition !== 'opted_out' && condition !== 'enabled') ||
      (packageCondition !== 'inactive' && packageCondition !== 'active') ||
      (condition === 'unavailable') !== (packageCondition === 'inactive')) {
    throw new Error('Invalid telemetry resource configuration')
  }
  if (config.replicate !== 1 && config.replicate !== 2) throw new Error('Invalid telemetry resource configuration')
  const label = `r${config.replicate}-${condition}`
  if (config.label !== label || config.probe_entry !== PROBE_ENTRY) throw new Error('Invalid telemetry resource configuration')
  if (typeof config.source !== 'string' || !/^[0-9a-f]{40}$/.test(config.source) ||
      typeof config.package_sha256 !== 'string' || !/^[0-9a-f]{64}$/.test(config.package_sha256) ||
      typeof config.spaceId !== 'string' || !/^[a-f0-9-]{36}$/.test(config.spaceId)) {
    throw new Error('Invalid telemetry resource configuration')
  }
  if (typeof config.credential !== 'string' || config.credential.length < 16 || config.credential.length > 256 ||
      /\s/.test(config.credential)) throw new Error('Invalid telemetry resource configuration')
  return {
    endpoint: loopbackOrigin(config.endpoint),
    spaceId: config.spaceId,
    credential: config.credential,
    label,
    condition,
    replicate: config.replicate as 1 | 2,
    source: config.source,
    package_condition: packageCondition,
    package_sha256: config.package_sha256,
  }
}

function connectScript(fixture: { endpoint: string; credential: string }): string {
  return `(async () => {
    const fixture = ${JSON.stringify({ endpoint: fixture.endpoint, credential: fixture.credential })};
    const bridge = window.mnemion;
    if (typeof bridge?.workspaceConnect !== 'function' || typeof bridge?.workspaceResume !== 'function') {
      throw new Error('The packaged workspace bridge is unavailable');
    }
    const session = await bridge.workspaceConnect({ endpoint: fixture.endpoint, credential: fixture.credential, remember: false });
    if (!session?.sessionToken || session.remembered) throw new Error('Session-only native connection required');
    if (!/^mnm_session_[A-Za-z0-9_-]{43}$/.test(session.sessionToken)) throw new Error('Renderer received a workspace key instead of a handle');
    return { connected: true, remembered: false, native_handle_only: true };
  })()`
}

function clientScript(): string {
  return `(async () => {
    const session = await window.mnemion.workspaceResume();
    if (!session?.sessionToken || session.remembered) throw new Error('Session-only native connection required');
    const { MnemionClient, measuredStudioClient, nativeFetch } = await import(${JSON.stringify(PROBE_ENTRY)});
    window.__mnemionMemoryProbe = { client: measuredStudioClient(new MnemionClient({
      baseUrl: session.endpoint, apiKey: session.sessionToken, retries: 0, fetch: nativeFetch,
    })), latencies: [], cycles: 0 };
    return { ready: true };
  })()`
}

function cyclesScript(number: number, spaceId: string): string {
  return `(async () => {
    const cycle = ${canonicalMemoryCycles.toString()};
    await cycle({ number: ${number}, space: ${JSON.stringify(spaceId)} });
    const probe = window.__mnemionMemoryProbe;
    return probe && Number.isInteger(probe.cycles) ? probe.cycles : null;
  })()`
}

function resultScript(): string {
  return `(async () => {
    const probe = window.__mnemionMemoryProbe;
    const sorted = [...probe.latencies].sort((a, b) => a - b);
    return { memory_cycles: probe.cycles, memory_results_verified: probe.cycles === 128,
      latency_p50_ms: sorted[Math.floor(sorted.length / 2)], latency_p99_ms: sorted[Math.floor(sorted.length * .99)] };
  })()`
}

async function verifiedCycles(window: BrowserWindow): Promise<number | undefined> {
  try {
    const count = await window.webContents.executeJavaScript(`(() => {
      const probe = window.__mnemionMemoryProbe
      return probe && Number.isInteger(probe.cycles) && probe.cycles >= 0 && probe.cycles <= 128 ? probe.cycles : null
    })()`)
    return Number.isInteger(count) ? count : undefined
  } catch {
    return undefined
  }
}

export async function verifyInstalledTelemetryResource(window: BrowserWindow, config: Record<string, unknown>): Promise<Record<string, unknown>> {
  if (!app.isPackaged) throw new Error('Installed telemetry resource workload requires the packaged application')
  const fixture = resourceConfig(config)
  let progress: { verified?: number; progressKnown: boolean } = { progressKnown: false }
  const settleCount = (count: unknown) => {
    progress = resourceProgress(progress, { settled: typeof count === 'number' ? count : undefined })
  }
  const markInflight = () => {
    progress = resourceProgress(progress, 'inflight')
    if (persistedPhase && Number.isInteger(progress.verified)) {
      marker(persistedPhase, progress.verified, false)
    }
  }
  try {
    marker('starting')
    marker('measuring')
    marker('before_workspace_connect')
    const connected = await window.webContents.executeJavaScript(connectScript(fixture))
    if (connected?.native_handle_only !== true || connected.remembered !== false) throw new Error('Session-only native connection required')
    marker('workspace_connected')
    const ready = await window.webContents.executeJavaScript(clientScript())
    if (ready?.ready !== true) throw new Error('The packaged memory client did not start')
    markInflight()
    settleCount(await window.webContents.executeJavaScript(cyclesScript(1, fixture.spaceId)))
    await settleInstalledTelemetryDelivery()
    marker('first_memory_cycle_and_delivery')
    for (const [number, completed] of canonicalRemainingBatches(true)) {
      markInflight()
      settleCount(await window.webContents.executeJavaScript(cyclesScript(number, fixture.spaceId)))
      await settleInstalledTelemetryDelivery()
      marker(`${completed}_memory_cycles`)
    }
    const result = await window.webContents.executeJavaScript(resultScript())
    settleCount(result?.memory_cycles)
    marker('finished', progress.verified, progress.progressKnown)
    if (!result || result.memory_results_verified !== true || result.memory_cycles !== progress.verified) {
      throw new Error('Canonical memory workload did not complete')
    }
    const evidence = {
      ...result,
      checkpoints: [...CHECKPOINTS],
      condition: fixture.condition,
      replicate: fixture.replicate,
      label: fixture.label,
      source: fixture.source,
      package_condition: fixture.package_condition,
      package_sha256: fixture.package_sha256,
      connected: true,
      packaged: true,
      runtime: {
        electron: process.versions.electron,
        node: process.versions.node,
        platform: process.platform,
        arch: process.arch,
        packaged: app.isPackaged,
      },
      model_calls: 0,
      forced_gc: false,
      idle_padding: false,
      memory_api_operations: 384,
      production_collection_available: false,
      resource_acceptance: false,
      qualification: 'installed resource workload',
    }
    const serialized = JSON.stringify(evidence)
    if (serialized.includes(fixture.credential) || serialized.includes('PRIVATE_RENDERER_MEMORY_CANARY')) {
      throw new Error('Resource evidence contained private fixture material')
    }
    return evidence
  } catch (error) {
    try {
      const reached = await verifiedCycles(window)
      if (reached !== undefined) progress = resourceProgress(progress, { settled: reached })
    } catch { /* A failed query keeps the last trustworthy count and leaves the total unknown. */ }
    try { marker('failed', progress.verified, progress.progressKnown) } catch { /* Keep the original failure. */ }
    throw error
  } finally {
    try { marker('closed', progress.verified, progress.progressKnown) } catch { /* Keep the original failure. */ }
  }
}
