/** Owned compiled-source diagnostic. Never loads an installed user profile. */
import { readFileSync, writeFileSync, renameSync } from 'node:fs'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import { setTimeout as delay } from 'node:timers/promises'

const root = process.env.MNEMION_STUDIO_USER_DATA
if (!root?.includes('mnemion-owned-renderer-')) throw new Error('Disposable renderer profile required')
const input = JSON.parse(readFileSync(join(root, 'probe-input.json'), 'utf8'))
if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(input.memory.base_url) ||
    !/^https:\/\/localhost:\d+\/v1\/report$/.test(input.destination) ||
    !/^\/assets\/[A-Za-z0-9._-]+\.js$/.test(input.probe_entry)) throw new Error('Owned loopback fixtures required')
const application = join(root, 'source/studio/electron')
const marker = value => {
  const file = join(root, 'monitor.json')
  writeFileSync(file + '.tmp', JSON.stringify({ at_ms: Date.now(), ...value }))
  renameSync(file + '.tmp', file)
}

async function bootstrap() {
  const { app } = await import('electron')
  const { DesktopTelemetryActivity } = await import('./dist/telemetry-activity.js')
  const stores = new Set(), writes = new Set()
  const counts = { snapshots: 0, accepted_writes: 0, reserved_attempts: 0 }
  const prototype = DesktopTelemetryActivity.prototype
  // Observe the actual bridge-owned instance. No replacement store, policy,
  // pressure gauge, admission result or transport is supplied by this probe.
  const snapshot = prototype.snapshot, record = prototype.recordMany, reserve = prototype.reserve
  prototype.snapshot = function (...args) { stores.add(this); counts.snapshots++; return snapshot.apply(this, args) }
  prototype.recordMany = async function (...args) {
    stores.add(this)
    const pending = record.apply(this, args)
    writes.add(pending)
    try { const accepted = await pending; counts.accepted_writes += Number(accepted); return accepted }
    finally { writes.delete(pending) }
  }
  prototype.reserve = async function (...args) {
    stores.add(this)
    const report = await reserve.apply(this, args)
    counts.reserved_attempts += Number(Boolean(report))
    return report
  }
  globalThis.__mnemionOwnedProbe = {
    counts,
    sample: name => ({ name, at_ms: Date.now(), main: process.memoryUsage(),
      processes: app.getAppMetrics().map(value => ({ pid: value.pid, type: value.type,
        name: value.name, cpu_ms: Number.isFinite(value.cpu.cumulativeCPUUsage) ? value.cpu.cumulativeCPUUsage * 1000 : null,
        working_set_bytes: value.memory.workingSetSize * 1024,
        peak_working_set_bytes: value.memory.peakWorkingSetSize * 1024 })),
    }),
    settle: async () => {
      while (writes.size) await Promise.all([...writes])
      await Promise.all([...stores].map(store => store.deliverySettled()))
    },
  }
  await import('./dist/application.js')
}

async function controller() {
  if (!process.env.MNEMION_PROBE_PLAYWRIGHT) throw new Error('Explicit Playwright module path required')
  const { _electron } = await import(pathToFileURL(process.env.MNEMION_PROBE_PLAYWRIGHT).href)
  const environment = { ...process.env }
  delete environment.ELECTRON_RUN_AS_NODE
  const electron = await _electron.launch({ executablePath: process.env.MNEMION_PROBE_ELECTRON,
    args: [application], cwd: application, env: environment, timeout: 30000 })
  const pid = electron.process().pid
  const samples = [], pageErrors = []
  let page
  try {
    marker({ phase: 'starting', pid })
    // Development mode also opens DevTools. Its window can win firstWindow(),
    // so select the app's owned origin instead of racing window creation.
    const deadline = Date.now() + 30000
    while (!page && Date.now() < deadline) {
      page = electron.windows().find(value => value.url().startsWith(`http://127.0.0.1:${process.env.VITE_DEV_PORT}/`))
      if (!page) await delay(25)
    }
    if (!page) throw new Error('Owned app window did not load its frontend')
    page.on('pageerror', error => pageErrors.push(error.name))
    console.log(JSON.stringify({ stage: 'first_window', url: page.url() }))
    page.setDefaultTimeout(20000)
    await page.getByRole('heading', { name: 'Welcome to Mnemion' }).waitFor()
    await electron.evaluate(({ webContents }) => {
      for (const contents of webContents.getAllWebContents()) if (contents.isDevToolsOpened()) contents.closeDevTools()
    })
    const initial = await page.locator('body').ariaSnapshot()
    writeFileSync(join(process.env.MNEMION_PROBE_ARTIFACTS, `${input.variant}-onboarding.txt`), initial)
    const bridge = await page.evaluate(() => ({
      available: typeof window.mnemion?.productTelemetrySnapshot === 'function' &&
        typeof window.mnemion?.productTelemetryRecord === 'function' && typeof window.mnemion?.serviceRequest === 'function',
      node_integration: typeof window.require !== 'undefined',
    }))
    if (!bridge.available || bridge.node_integration) throw new Error('Actual sandboxed preload is unavailable')
    const sample = async name => {
      const value = await electron.evaluate((_electron, name) => globalThis.__mnemionOwnedProbe.sample(name), name)
      samples.push(value)
    }
    // The interval includes first connection and cold telemetry work. No forced
    // GC, synthetic idle interval or resource-admission replacement is used.
    marker({ phase: 'measuring', pid })
    await sample('before_workspace_connect')
    await page.getByRole('button', { name: 'Join a workspace' }).click()
    writeFileSync(join(process.env.MNEMION_PROBE_ARTIFACTS, `${input.variant}-join.txt`), await page.locator('body').ariaSnapshot())
    await page.getByLabel('Workspace address', { exact: true }).fill(input.memory.base_url)
    await page.getByLabel('Workspace key', { exact: true }).fill(input.memory.api_key)
    const remember = page.getByRole('checkbox', { name: 'Remember this workspace on this device' })
    if (await remember.isEnabled()) await remember.uncheck()
    await page.getByRole('form', { name: 'Connect a workspace' }).getByRole('button', { name: 'Open workspace', exact: true }).click()
    await page.getByRole('heading', { name: 'Welcome to Mnemion' }).waitFor({ state: 'hidden' })
    await sample('workspace_connected')
    const connection = await page.evaluate(async entry => {
      const session = await window.mnemion.workspaceResume()
      if (!session?.sessionToken || session.remembered) throw new Error('Session-only native connection required')
      const { MnemionClient, measuredStudioClient, nativeFetch } = await import(entry)
      window.__mnemionMemoryProbe = { client: measuredStudioClient(new MnemionClient({
        baseUrl: session.endpoint, apiKey: session.sessionToken, retries: 0, fetch: nativeFetch,
      })), latencies: [], cycles: 0 }
      return { native_handle_only: /^mnm_session_[A-Za-z0-9_-]{43}$/.test(session.sessionToken), remembered: session.remembered }
    }, input.probe_entry)
    if (!connection.native_handle_only) throw new Error('Renderer received a workspace key instead of a handle')
    async function cycles(number) {
      await page.evaluate(async ({ number, space }) => {
        const probe = window.__mnemionMemoryProbe
        for (let index = 0; index < number; index++) {
          const start = performance.now(), query = 'rendererprobe' + probe.cycles
          const content = (query + ' postgres backup billing procedure. ').repeat(20)
          const saved = await probe.client.save(space, { content, subject: 'PRIVATE_RENDERER_MEMORY_CANARY', kind: 'procedure' })
          if (!saved.lexical_ready || !saved.memory_id) throw new Error('Real save failed')
          const fetched = await probe.client.fetch(saved.memory_id)
          if (fetched.content !== content) throw new Error('Real fetch changed content')
          const recalled = await probe.client.search({ query, space_ids: [space], mode: 'lexical', limit: 5 })
          if (!recalled.hits.some(hit => hit.memory_id === saved.memory_id)) throw new Error('Real recall omitted the saved memory')
          probe.cycles++
          probe.latencies.push(performance.now() - start)
        }
      }, { number, space: input.memory.space_id })
    }
    await cycles(1)
    await electron.evaluate(async () => globalThis.__mnemionOwnedProbe.settle())
    await sample('first_memory_cycle_and_delivery')
    await cycles(31)
    await electron.evaluate(async () => globalThis.__mnemionOwnedProbe.settle())
    await sample('32_memory_cycles')
    await cycles(96)
    await electron.evaluate(async () => globalThis.__mnemionOwnedProbe.settle())
    await sample('128_memory_cycles')
    marker({ phase: 'finished', pid })
    const result = await page.evaluate(() => {
      const { latencies, cycles } = window.__mnemionMemoryProbe
      const sorted = [...latencies].sort((a, b) => a - b)
      return { memory_cycles: cycles, memory_results_verified: cycles === 128,
        latency_p50_ms: sorted[Math.floor(sorted.length / 2)], latency_p99_ms: sorted[Math.floor(sorted.length * .99)] }
    })
    const counts = await electron.evaluate(() => ({ ...globalThis.__mnemionOwnedProbe.counts }))
    const first = samples[0], last = samples.at(-1)
    const total = sample => sample.processes.reduce((sum, row) => sum + row.working_set_bytes, 0)
    writeFileSync(process.env.MNEMION_COST_RESULT, JSON.stringify({ schema_version: 1, variant: input.variant,
      ...result, ...counts, samples, bridge, connection, page_errors: pageErrors,
      runtime: await electron.evaluate(() => ({ electron: process.versions.electron, node: process.versions.node,
        platform: process.platform, arch: process.arch, packaged: false })),
      elapsed_ms: last.at_ms - first.at_ms, rss_delta_bytes: total(last) - total(first),
      sampled_peak_rss_delta_bytes: Math.max(...samples.map(total)) - total(first),
      memory_api_operations: result.memory_cycles * 3, forced_gc: false, idle_padding: false,
      qualification: 'Compiled source UI with real app onboarding, shared renderer SDK and sandboxed IPC; fixed synthetic memory work. Electron working-set sums double-count shared pages. External sampler also covers observed helper descendants. Not installed-platform, stable resource-ceiling, embedding-quality or whole-wire acceptance.',
      production_collection_available: false, model_calls: 0,
    }, null, 2) + '\n', { flag: 'wx' })
  } catch (error) {
    const failure = { url: page?.url(), page_errors: pageErrors, windows: electron.windows().map(value => value.url()) }
    try { failure.dom = await page?.locator('body').ariaSnapshot({ timeout: 3000 }) } catch { /* Retain the original failure. */ }
    writeFileSync(join(process.env.MNEMION_PROBE_ARTIFACTS, `${input.variant}-failure.json`), JSON.stringify(failure, null, 2) + '\n')
    throw error
  } finally {
    // close() awaits the actual app lifecycle rather than abandoning Chromium.
    await electron.close()
    marker({ phase: 'closed', pid })
  }
}

if (process.versions.electron) await bootstrap()
else {
  // The app and measurement entry share one compiled module graph, served as
  // static files. No development compiler runs during the measured interval.
  await controller().catch(error => { console.error(error); process.exitCode = 1 })
}
