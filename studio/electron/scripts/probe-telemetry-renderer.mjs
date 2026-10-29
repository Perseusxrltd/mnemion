/** Owned compiled-source diagnostic. Never loads an installed user profile. */
import { readFileSync, writeFileSync, renameSync } from 'node:fs'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import { setTimeout as delay } from 'node:timers/promises'
import { readBoundedLinuxStatus, selectHeap, unavailableLinux } from './phase-memory.mjs'

const root = process.env.MNEMION_STUDIO_USER_DATA
if (!root?.includes('mnemion-owned-renderer-')) throw new Error('Disposable renderer profile required')
const input = JSON.parse(readFileSync(join(root, 'probe-input.json'), 'utf8'))
if (input.phase_memory === true && (input.comparison !== true || input.attribution === true)) {
  throw new Error('Phase-memory counters require comparison without attribution')
}
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
  const { app, BrowserWindow, webContents } = await import('electron')
  const allocation = { samples: [], calls: {}, errors: [], enabled: input.attribution === true }
  const phaseMemory = input.phase_memory === true
  const heapStatistics = allocation.enabled || phaseMemory
    ? (await import('node:v8')).getHeapStatistics : null
  const capture = name => {
    if (!allocation.enabled || allocation.samples.length >= 32) return
    try {
      // Only fixed numeric fields: no mappings, paths, network identifiers or
      // application data. This instrumentation is diagnostic overhead, not a
      // resource qualification or a replacement for RSS accounting.
      const linux = process.platform === 'linux' ? readBoundedLinuxStatus() : {}
      allocation.samples.push({ name, at_ms: Date.now(), monotonic_ms: performance.now(),
        main: process.memoryUsage(), heap: heapStatistics(), os_usage: process.resourceUsage(), linux })
    } catch (error) { allocation.errors.push({ name, error: error.name }) }
  }
  const phaseMemorySnapshot = () => {
    // IO and statistic failures stay null. They are unavailable, not zero,
    // and the error text is not retained.
    let linux = unavailableLinux()
    let heap = selectHeap(null)
    try { linux = readBoundedLinuxStatus() } catch { linux = unavailableLinux() }
    try { heap = selectHeap(heapStatistics ? heapStatistics() : null) } catch { heap = selectHeap(null) }
    return { linux, heap }
  }
  const observeFirst = (prototype, method, name) => {
    const original = prototype[method]
    if (typeof original !== 'function') throw new Error(`Missing owned attribution method: ${name}`)
    prototype[method] = function (...args) {
      const first = !allocation.calls[name]
      allocation.calls[name] = (allocation.calls[name] ?? 0) + 1
      if (!first) return original.apply(this, args)
      capture(`${name}.before`)
      let value
      try { value = original.apply(this, args) }
      catch (error) { capture(`${name}.error`); throw error }
      if (value && typeof value.then === 'function') return value.then(
        result => { capture(`${name}.after`); return result },
        error => { capture(`${name}.error`); throw error })
      capture(`${name}.after`)
      return value
    }
  }
  capture('bootstrap.before_telemetry_imports')
  const { DesktopTelemetryActivity } = await import('./dist/telemetry-activity.js')
  const { ProductTelemetry } = await import('./dist/product-telemetry.js')
  const setupControls = { schema_version: 1, attempts: 0, completed: 0, failed: 0,
    in_flight: 0, overflow: false, replies: [] }
  const controls = ProductTelemetry.prototype.execute
  const flag = value => typeof value === 'boolean' ? value : null
  const choice = (value, allowed) => allowed.includes(value) ? value : null
  // Observe the real setup request, without replacing its response, changing
  // consent, waiting before the first sample or recording local generations.
  ProductTelemetry.prototype.execute = async function (action, ...args) {
    if (action !== 'telemetry.status') return controls.call(this, action, ...args)
    if (setupControls.attempts >= 16) {
      setupControls.overflow = true
      return controls.call(this, action, ...args)
    }
    setupControls.attempts++; setupControls.in_flight++
    try {
      const value = await controls.call(this, action, ...args)
      setupControls.completed++
      setupControls.replies.push({
        schema_version: value?.schema_version === 1 ? 1 : null,
        user_enabled: flag(value?.user_enabled), effective_enabled: flag(value?.effective_enabled),
        collection_available: flag(value?.collection_available),
        storage: choice(value?.storage, ['new', 'ready', 'unreadable']),
        reason: choice(value?.reason, ['enabled', 'user_disabled', 'storage_unavailable',
          'coordination_unavailable', 'browser_privacy', 'company_policy', 'disclosure_required', 'collection_unavailable']),
        connection_mode: choice(value?.connection_mode, ['auto', 'unmetered', 'metered']),
        disclosure_acknowledged: Number.isInteger(value?.required_disclosure_version) &&
          value.required_disclosure_version > 0 && value.disclosure_version === value.required_disclosure_version,
        store_generation_valid: typeof value?.store_generation === 'string' && /^[0-9a-f]{32}$/.test(value.store_generation),
      })
      return value
    } catch (error) { setupControls.failed++; throw error }
    finally { setupControls.in_flight-- }
  }
  if (allocation.enabled) {
    const { NativeTelemetryStore } = await import('./dist/telemetry-store.js')
    const { NativeTelemetryDelivery } = await import('./dist/telemetry-delivery.js')
    const { NativeNetworkConditions } = await import('./dist/telemetry-network.js')
    const { DesktopTelemetryConditions } = await import('./dist/telemetry-conditions.js')
    capture('bootstrap.after_telemetry_imports')
    observeFirst(NativeTelemetryStore.prototype, 'open', 'sqlite.open')
    observeFirst(NativeTelemetryStore.prototype, 'closeDatabase', 'sqlite.close')
    observeFirst(NativeNetworkConditions.prototype, 'start', 'network_cost.start')
    observeFirst(DesktopTelemetryConditions.prototype, 'prepare', 'conditions.prepare')
    observeFirst(NativeTelemetryDelivery.prototype, 'reserve', 'delivery.reserve')
    // The transport uses one literal-address socket. Observe only that owned
    // loopback destination, leaving connection arguments and behavior intact.
    const { Socket } = await import('node:net')
    const connect = Socket.prototype.connect, destination = new URL(input.destination)
    Socket.prototype.connect = function (...args) {
      if (args[0]?.host === '127.0.0.1' && args[0]?.port === Number(destination.port)) {
        allocation.calls['transport.socket'] = (allocation.calls['transport.socket'] ?? 0) + 1
        if (allocation.calls['transport.socket'] === 1) {
          capture('transport.before_connect')
          this.once('close', () => capture('transport.after_close'))
        }
      }
      return connect.apply(this, args)
    }
  }
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
  const processSample = name => {
    const windows = BrowserWindow.getAllWindows().filter(window => !window.isDestroyed())
    const owned = windows.filter(window => window.webContents.getURL().startsWith(`http://127.0.0.1:${process.env.VITE_DEV_PORT}/`))
    const renderer = owned.length === 1 ? owned[0].webContents.getOSProcessId() : null
    const contents = webContents.getAllWebContents().filter(value => !value.isDestroyed())
    const devtools = contents.some(value => value.isDevToolsOpened() || /^(?:chrome-)?devtools:/.test(value.getURL()))
    const metrics = app.getAppMetrics()
    const tabs = metrics.filter(value => value.type === 'Tab')
    const ownership = { schema_version: 1, main_pid: process.pid, renderer_pid: renderer,
      app_windows: owned.length, all_windows: windows.length, devtools_present: devtools,
      web_contents: contents.map(value => ({ pid: value.getOSProcessId(), type: value.getType(),
        app: owned.length === 1 && value === owned[0].webContents,
        devtools: /^(?:chrome-)?devtools:/.test(value.getURL()) })),
      renderer_processes: tabs.length, valid: windows.length === 1 && owned.length === 1 && !devtools &&
        tabs.length === 1 && tabs[0].pid === renderer &&
        metrics.filter(value => value.type === 'Browser').length === 1 &&
        metrics.some(value => value.type === 'Browser' && value.pid === process.pid) }
    const sample = { name, at_ms: Date.now(), main: process.memoryUsage(), ownership,
      setup_controls: { attempts: setupControls.attempts, completed: setupControls.completed,
        failed: setupControls.failed, in_flight: setupControls.in_flight },
      processes: metrics.map(value => ({ pid: value.pid, type: value.type,
        role: value.pid === process.pid ? 'app_main' : value.pid === renderer ? 'app_renderer' : value.type,
        name: value.name, cpu_ms: Number.isFinite(value.cpu.cumulativeCPUUsage) ? value.cpu.cumulativeCPUUsage * 1000 : null,
        working_set_bytes: value.memory.workingSetSize * 1024,
        peak_working_set_bytes: value.memory.peakWorkingSetSize * 1024 })),
    }
    if (phaseMemory) sample.phase_memory = phaseMemorySnapshot()
    return sample
  }
  globalThis.__mnemionOwnedProbe = {
    counts,
    setupControls,
    allocation,
    sample: processSample,
    settle: async () => {
      while (writes.size) await Promise.all([...writes])
      await Promise.all([...stores].map(store => store.deliverySettled()))
    },
  }
  await import('./dist/application.js')
}

async function controller() {
  if (!process.env.MNEMION_PROBE_PLAYWRIGHT) throw new Error('Explicit Playwright module path required')
  if (process.env.MNEMION_STUDIO_DEVTOOLS !== '0') throw new Error('Disable development DevTools before app startup')
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
    // Select the app's owned origin. Each measurement independently verifies
    // the renderer PID and refuses any extra renderer or debugger window.
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
      marker({ phase: name, pid })
      if (!value.ownership.valid) throw new Error('Resource sample has an unexpected or unowned app process')
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
    const remaining = input.attribution || input.comparison ? [[7, 8], [8, 16], [16, 32], [32, 64], [32, 96], [32, 128]] : [[31, 32], [96, 128]]
    for (const [number, completed] of remaining) {
      await cycles(number)
      await electron.evaluate(async () => globalThis.__mnemionOwnedProbe.settle())
      await sample(`${completed}_memory_cycles`)
    }
    marker({ phase: 'finished', pid })
    const result = await page.evaluate(() => {
      const { latencies, cycles } = window.__mnemionMemoryProbe
      const sorted = [...latencies].sort((a, b) => a - b)
      return { memory_cycles: cycles, memory_results_verified: cycles === 128,
        latency_p50_ms: sorted[Math.floor(sorted.length / 2)], latency_p99_ms: sorted[Math.floor(sorted.length * .99)] }
    })
    const counts = await electron.evaluate(() => ({ ...globalThis.__mnemionOwnedProbe.counts }))
    const setupControls = await electron.evaluate(() => globalThis.__mnemionOwnedProbe.setupControls)
    const allocation = await electron.evaluate(() => globalThis.__mnemionOwnedProbe.allocation)
    const first = samples[0], last = samples.at(-1)
    const total = sample => sample.processes.reduce((sum, row) => sum + row.working_set_bytes, 0)
    writeFileSync(process.env.MNEMION_COST_RESULT, JSON.stringify({ schema_version: 1, variant: input.variant,
      ...result, ...counts, samples, bridge, connection, page_errors: pageErrors,
      setup_controls: setupControls,
      condition: input.condition ?? input.variant, replicate: input.replicate ?? 1, allocation,
      comparison: input.comparison === true, phase_memory: input.phase_memory === true,
      devtools_auto_open: false,
      process_ownership_verified: samples.every(sample => sample.ownership.valid),
      runtime: await electron.evaluate(() => ({ electron: process.versions.electron, node: process.versions.node,
        platform: process.platform, arch: process.arch, packaged: false })),
      elapsed_ms: last.at_ms - first.at_ms, rss_delta_bytes: total(last) - total(first),
      sampled_peak_rss_delta_bytes: Math.max(...samples.map(total)) - total(first),
      memory_api_operations: result.memory_cycles * 3, forced_gc: false, idle_padding: false,
      qualification: 'Compiled source UI with real app onboarding, shared renderer SDK and sandboxed IPC; fixed synthetic memory work. Electron working-set sums double-count shared pages. External sampler also covers observed helper descendants. Not installed-platform, stable resource-ceiling, embedding-quality or whole-wire acceptance.'
        + (input.phase_memory === true
          ? ' Phase-memory counters are an opt-in main-process diagnostic and do not replace or pass the working-set gate.'
          : ''),
      production_collection_available: false, model_calls: 0,
    }, null, 2) + '\n', { flag: 'wx' })
  } catch (error) {
    const failure = { url: page?.url(), page_errors: pageErrors, windows: electron.windows().map(value => value.url()), samples }
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
else if (input.review_journey) {
  const { reviewController } = await import('./probe-telemetry-review.mjs')
  await reviewController({ root, input, application, marker }).catch(error => { console.error(error); process.exitCode = 1 })
} else {
  // The app and measurement entry share one compiled module graph, served as
  // static files. No development compiler runs during the measured interval.
  await controller().catch(error => { console.error(error); process.exitCode = 1 })
}
