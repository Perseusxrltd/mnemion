/** Diagnostic only: real headless app, private local queue and loopback collector. */
import { app, net, powerMonitor } from 'electron'
import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import { setTimeout as delay } from 'node:timers/promises'

const repository = process.env.MNEMION_PROBE_SOURCE
const fixture = process.env.MNEMION_STUDIO_USER_DATA
if (!repository || !fixture?.includes('mnemion-owned-pipeline-')) throw new Error('An isolated resource fixture is required')
const input = JSON.parse(readFileSync(join(fixture, 'probe-input.json'), 'utf8'))
if (!/^https:\/\/localhost:\d+\/v3\/report$/.test(input.destination)) throw new Error('Loopback collector required')
if (input.memory && !/^http:\/\/127\.0\.0\.1:\d+$/.test(input.memory.base_url)) throw new Error('Disposable loopback workspace required')
await import(pathToFileURL(join(repository, 'studio/electron/dist/application.js')).href)

async function measure() {
  await app.whenReady()
  const deadline = Date.now() + 15000
  let startup
  for (;;) {
    if (Date.now() > deadline) throw new Error('Isolated app bootstrap timed out')
    if (existsSync(process.env.MNEMION_STUDIO_SMOKE_FILE)) {
      startup = JSON.parse(readFileSync(process.env.MNEMION_STUDIO_SMOKE_FILE, 'utf8'))
      if (startup.stage === 'client-ready') break
      if (['startup-error', 'uncaught-exception', 'unhandled-rejection'].includes(startup.stage)) throw new Error('Isolated bootstrap failed')
    }
    await delay(50)
  }
  // Only normal already-started bootstrap settles here. This is outside every
  // measured interval, and no telemetry component is activated beforehand.
  await delay(1500)
  const samples = []
  const sample = name => {
    const memory = process.memoryUsage(), cpu = process.cpuUsage()
    samples.push({ name, at_ms: performance.now(), cpu_ms: (cpu.user + cpu.system) / 1000,
      rss: memory.rss, heap: memory.heapUsed, external: memory.external,
      active_resource_types: process.getActiveResourcesInfo().sort() })
  }
  sample('app_ready_before_activation')
  const { DesktopTelemetryActivity } = await import(pathToFileURL(join(repository, 'studio/electron/dist/telemetry-activity.js')).href)
  const { DesktopTelemetryConditions } = await import(pathToFileURL(join(repository, 'studio/electron/dist/telemetry-conditions.js')).href)
  const { nativeTelemetryDefinitions } = await import(pathToFileURL(join(repository, 'studio/electron/dist/telemetry-store.js')).href)
  const { TelemetryWorkflow } = await import(pathToFileURL(join(repository, 'studio/electron/dist/telemetry-workflow.js')).href)
  const { NativeNetworkConditions } = await import(pathToFileURL(join(repository, 'studio/electron/dist/telemetry-network.js')).href)
  const definitions = nativeTelemetryDefinitions()
  if (definitions.disclosure.collection_available !== false || definitions.disclosure.destination !== null) throw new Error('Unexpected production activation')
  let networkReads = 0, acceptedWrites = 0, snapshots = 0, attempts = 0
  const producerWrites = new Set()
  const network = new NativeNetworkConditions()
  const gauges = new DesktopTelemetryConditions({ online: () => net.isOnline(), thermal: () => powerMonitor.getCurrentThermalState() }, network)
  const conditions = []
  class ObservedActivity extends DesktopTelemetryActivity {
    snapshot(...args) { snapshots++; return super.snapshot(...args) }
    async recordMany(values, stamp, day) {
      const pending = super.recordMany(values, stamp, day)
      producerWrites.add(pending)
      try { const result = await pending; acceptedWrites += Number(result); return result }
      finally { producerWrites.delete(pending) }
    }
    async reserve(...args) { const report = await super.reserve(...args); attempts += Number(Boolean(report)); return report }
  }
  const activeStore = new ObservedActivity(join(fixture, 'mnemion-product-telemetry'),
    { ...definitions.disclosure, collection_available: input.available, destination: input.destination },
    definitions.catalog, () => {
      const value = gauges.read(); networkReads++
      if (conditions.length < 32) conditions.push(value)
      return value
    }, join(fixture, 'company-absent.json'), '127.0.0.1', {
      prepare: stop => gauges.prepare(stop), close: () => gauges.close(),
    }, input.certificate_authorities)
  sample('owner_created')
  const latencies = []
  let memoryCycles = 0, memoryResultsVerified = false
  let memoryClient
  if (input.memory) {
    const { MnemionClient, measuredStudioClient } = await import('./measured-studio-fixture.mjs')
    const { workspaceFetch } = await import(pathToFileURL(join(repository, 'studio/electron/dist/workspace-fetch.js')).href)
    memoryClient = measuredStudioClient(new MnemionClient({ baseUrl: input.memory.base_url, apiKey: input.memory.api_key, retries: 0,
      fetch: (url, options) => workspaceFetch(net.fetch.bind(net), String(url), options),
    }), activeStore, 'desktop')
  }
  const workflow = async () => {
    const started = performance.now()
    if (memoryClient) {
      const index = memoryCycles, query = 'memoryprobe' + index
      const content = (query + ' postgres backup billing procedure. ').repeat(20)
      const receipt = await memoryClient.save(input.memory.space_id, { content, subject: 'PRIVATE_MEMORY_CANARY', kind: 'procedure' })
      if (receipt.lexical_ready !== true || !receipt.memory_id) throw new Error('Disposable memory save was not accepted')
      const restored = await memoryClient.fetch(receipt.memory_id)
      if (restored.content !== content) throw new Error('Disposable memory fetch changed the content')
      const recalled = await memoryClient.search({ query, space_ids: [input.memory.space_id], mode: 'lexical', limit: 5 })
      if (!recalled.hits.some(hit => hit.memory_id === receipt.memory_id)) throw new Error('Disposable recall did not return the saved memory')
      memoryCycles++
    } else {
      const entry = await TelemetryWorkflow.begin(activeStore, 'memory.recall', 'desktop')
      await entry?.finish('success', 'none', { result_items: 1 })
    }
    latencies.push(performance.now() - started)
  }
  const settled = async () => {
    while (producerWrites.size) await Promise.all([...producerWrites])
    await activeStore.deliverySettled()
  }
  await workflow()
  sample('first_producer')
  await settled()
  sample('first_delivery_settled')
  for (let index = 1; index < 32; index++) await workflow()
  await settled()
  sample('daily_scope_saturated')
  for (let index = 0; index < (input.memory ? 96 : 512); index++) await workflow()
  await settled()
  sample(input.memory ? 'remaining_96_memory_cycles' : 'saturated_512_more_calls')
  memoryResultsVerified = memoryCycles === 128
  activeStore.closeDelivery()
  await activeStore.deliverySettled()
  sample('owner_closed')
  const first = samples[0], last = samples.at(-1)
  const sorted = [...latencies].sort((a, b) => a - b)
  writeFileSync(process.env.MNEMION_COST_RESULT, JSON.stringify({
    schema_version: 1, variant: input.variant, available: input.available, user_enabled: input.enabled,
    runtime: { electron: process.versions.electron, node: process.versions.node, platform: process.platform, arch: process.arch },
    bootstrap: startup.stage, samples, snapshots, accepted_writes: acceptedWrites, reserved_attempts: attempts,
    actual_condition_checks: networkReads, actual_conditions: conditions,
    workflows: latencies.length, latency_p50_ms: sorted[Math.floor(sorted.length / 2)], latency_p99_ms: sorted[Math.floor(sorted.length * .99)],
    elapsed_ms: last.at_ms - first.at_ms, cpu_ms: last.cpu_ms - first.cpu_ms,
    rss_delta_bytes: last.rss - first.rss, sampled_peak_rss_delta_bytes: Math.max(...samples.map(row => row.rss)) - first.rss,
    forced_gc: false, injected_cpu_or_memory_or_network_admission: false,
    connection_mode_declaration: 'unmetered',
    qualification: 'diagnostic_owned_pipeline_after_headless_real_app_bootstrap; burst_producer_workload_not_representative_memory_work; not_installed_or_whole_app_acceptance',
    production_collection_available: false, production_memory_calls: 0, model_calls: 0,
    ...(input.memory ? {
      memory_cycles: memoryCycles, memory_results_verified: memoryResultsVerified,
      memory_api_operations: memoryCycles * 3, latency_unit: 'three_operation_cycle',
      memory_workload: { cycles: 128, operations_per_cycle: ['save', 'fetch', 'lexical_recall'], server: 'disposable_postgresql_and_real_api',
        transport: 'actual_workspaceFetch_and_Electron_net_fetch_over_loopback_HTTP', model: '4D_protocol_fixture_no_model_service',
        producer: 'actual_measuredStudioClient_with_supplied_native_store_no_renderer_or_IPC', paced_or_idle_padding: false },
      process_scope: 'Electron_main_only; excludes_Chromium_network_service_API_and_PostgreSQL',
      qualification: 'diagnostic_real_memory_transactions_and_UI_owner_in_main_process; excludes_renderer_IPC_installed_platforms_whole_wire_and_embedding_quality',
    } : {}),
  }, null, 2) + '\n', { flag: 'wx' })
  app.quit()
}
void measure().catch(error => { console.error(error); app.exit(1) })
