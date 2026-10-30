/** An unavailable or timed-out check suppresses telemetry; it never repairs ACLs.
 * A missing readPrivateStore export refuses. This path does not spawn the helper. */
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { deliveryObservationEnabled, noteAcl } from './telemetry-observation-diagnostic.mjs'

const require = createRequire(import.meta.url)

export function windowsTelemetryPrivateExecutable(moduleUrl = import.meta.url): string {
  // spawn cannot execute an entry inside ASAR. Packaging explicitly keeps this
  // one native binary beside the archive; source runs use their ordinary dist.
  return fileURLToPath(new URL('./telemetry-private-store.exe', moduleUrl))
    .replace(/([\\/])app\.asar([\\/])/, '$1app.asar.unpacked$2')
}

export function privateStoreBindingPath(moduleUrl = import.meta.url): string {
  return fileURLToPath(new URL('./telemetry-network.node', moduleUrl))
    .replace(/([\\/])app\.asar([\\/])/, '$1app.asar.unpacked$2')
}

/** The export must be a function. Older, missing, and non-function values refuse. */
export function privateStoreReader(binding: unknown): ((root: string, database: string) => unknown) | null {
  if (!binding || typeof binding !== 'object') return null
  const read = (binding as { readPrivateStore?: unknown }).readPrivateStore
  return typeof read === 'function' ? read as (root: string, database: string) => unknown : null
}

export function privateStoreQuery(binding: unknown): (root: string, database: string) => unknown {
  const read = privateStoreReader(binding)
  if (!read) return () => 0
  return (root, database) => read(root, database)
}

let networkBinding: unknown | false | undefined
function loadNetworkBinding(): unknown {
  if (networkBinding === undefined) {
    try { networkBinding = require(privateStoreBindingPath()) }
    catch { networkBinding = false }
  }
  return networkBinding || null
}

function productionQuery(root: string, database: string): unknown {
  const read = privateStoreReader(loadNetworkBinding())
  if (!read) return 0
  return read(root, database)
}

/** One unsettled native call owns the slot, including after its deadline.
 * A later result cannot grant the timed-out call or stand in for a successor. */
export class WindowsTelemetryPrivateProbe {
  private settled?: Promise<unknown>
  constructor(private readonly query: (root: string, database: string) => unknown = productionQuery) {}

  read(root: string, database: string): Promise<boolean> {
    const diagnose = deliveryObservationEnabled()
    if (this.settled) {
      if (diagnose) noteAcl('refused', 0)
      return Promise.resolve(false)
    }
    const started = diagnose ? performance.now() : 0
    let task: Promise<unknown>
    try { task = Promise.resolve(this.query(root, database)) }
    catch {
      if (diagnose) noteAcl('refused', performance.now() - started)
      return Promise.resolve(false)
    }
    const gate = task
    this.settled = gate
    return new Promise(resolve => {
      let done = false, timer: ReturnType<typeof setTimeout> | undefined
      const finish = (accepted: boolean, outcome: 'accepted' | 'refused' | 'timed_out') => {
        if (done) return
        done = true
        clearTimeout(timer)
        if (diagnose) noteAcl(outcome, performance.now() - started)
        resolve(accepted)
      }
      const release = () => { if (this.settled === gate) this.settled = undefined }
      task.then(value => {
        release()
        finish(value === 1, value === 1 ? 'accepted' : 'refused')
      }, () => {
        release()
        finish(false, 'refused')
      })
      timer = setTimeout(() => finish(false, 'timed_out'), 1000)
      timer.unref()
    })
  }
}

const privateProbe = new WindowsTelemetryPrivateProbe()

export function windowsTelemetryPrivateStore(root: string, database: string): Promise<boolean> {
  return privateProbe.read(root, database)
}
