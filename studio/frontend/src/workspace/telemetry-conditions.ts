/** Bounded current browser capability checks; no guesses about a Wi-Fi tariff. */
type Connection = EventTarget & { saveData?: boolean; type?: string; effectiveType?: string }
type PressureRecord = { state: string; time: number }
type PressureObserverLike = { observe: (source: 'cpu', options: { sampleInterval: number }) => Promise<void>; disconnect: () => void }
type PressureConstructor = new (callback: (records: PressureRecord[]) => void) => PressureObserverLike
type HeapMemory = { usedJSHeapSize?: unknown; jsHeapSizeLimit?: unknown }
export type BrowserTelemetryConditions = { network: 'unknown' | 'metered' | 'unmetered'; constrained: boolean }
const freshPressure = (at: number): boolean => {
  const age = performance.now() - at
  return Number.isFinite(at) && at >= 0 && Number.isFinite(age) && age >= 0 && age <= 2000
}
const knownPressure = (state: unknown): state is 'nominal' | 'fair' | 'serious' | 'critical' =>
  state === 'nominal' || state === 'fair' || state === 'serious' || state === 'critical'
const capabilityRejection = (error: unknown): boolean => {
  const name = error && typeof error === 'object' ? (error as { name?: unknown }).name : undefined
  return name === 'NotSupportedError' || name === 'NotAllowedError'
}

export class BrowserConditions {
  private pressure: string | null = null
  private observedAt = -Infinity
  private observer?: PressureObserverLike
  private generation = 0
  /** Capability, kept apart from the latest reading. */
  private pressureAvailability: 'unknown' | 'unavailable' | 'supported' = 'unknown'
  /** A real non-nominal reading stays until a later fresh nominal reading. */
  private pressureRestricted = false
  /** A real heap reading at or above 80% stays until a later valid lower reading. */
  private heapRestricted = false
  /** Known connection restrictions survive a missing API, a partial report and close(). */
  private saveDataRestricted = false
  private cellularRestricted = false
  private slowLinkRestricted = false

  connection(): Connection | undefined {
    return (navigator as Navigator & { connection?: Connection }).connection
  }
  read(): BrowserTelemetryConditions {
    try {
      const signals = this.connectionLimited()
      const heapLimited = this.heapLimited()
      // Data-saving mode and a cellular connection are treated conservatively.
      // Ethernet/Wi-Fi and saveData=false never imply an unmetered plan.
      return { network: signals.metered ? 'metered' : 'unknown', constrained:
        navigator.onLine !== true || document.visibilityState !== 'visible' || signals.metered ||
        signals.slow || signals.refused || this.pressureLimited() || heapLimited }
    } catch {
      return { network: this.saveDataRestricted || this.cellularRestricted ? 'metered' : 'unknown', constrained: true }
    }
  }
  async start(stop: AbortSignal): Promise<boolean> {
    this.detach()
    if (stop.aborted) return false
    const Constructor = (globalThis as typeof globalThis & { PressureObserver?: PressureConstructor }).PressureObserver
    // Absence is a capability limit. It does not invent a nominal reading or
    // erase a restriction that was already observed.
    if (!Constructor) {
      this.pressureAvailability = 'unavailable'
      return !this.pressureRestricted
    }
    const generation = this.generation
    let timer: ReturnType<typeof setTimeout> | undefined, settled = false
    let finish = (_value: boolean) => {}
    const ready = new Promise<boolean>(resolve => {
      finish = value => { if (!settled) { settled = true; resolve(value) } }
    })
    const aborted = () => { this.detach(); finish(false) }
    const refuse = (error?: unknown) => {
      if (generation !== this.generation) return
      if (capabilityRejection(error)) {
        this.detach()
        this.pressureAvailability = 'unavailable'
        finish(!this.pressureRestricted && !stop.aborted)
        return
      }
      // A timeout, bad reading or unexpected failure is not "unsupported".
      this.pressureAvailability = 'supported'
      this.detach()
      finish(false)
    }
    try {
      this.pressureAvailability = 'supported'
      this.observer = new Constructor(records => {
        if (generation !== this.generation || stop.aborted) return
        // finish() may already be settled. Drop the fresh window anyway, and
        // keep an earlier real pressure restriction.
        if (!Array.isArray(records)) {
          this.pressure = null
          this.observedAt = -Infinity
          finish(false)
          return
        }
        if (!records.length) return
        const latest = records[records.length - 1]
        if (!latest || !knownPressure(latest.state) || !freshPressure(latest.time)) {
          this.pressure = null
          this.observedAt = -Infinity
          finish(false)
          return
        }
        this.pressure = latest.state
        this.observedAt = latest.time
        this.pressureRestricted = latest.state !== 'nominal'
        finish(latest.state === 'nominal')
      })
      stop.addEventListener('abort', aborted, { once: true })
      // Chromium's first OS reading can arrive after one second even when a
      // shorter sample interval is requested. Allow bounded initialization
      // before reservation; fresh nominal pressure and cancellation still apply.
      // Only during newly offered awake work, never a periodic/idle observer.
      timer = setTimeout(() => refuse(), 3000)
      try {
        void Promise.resolve(this.observer.observe('cpu', { sampleInterval: 250 })).catch(error => refuse(error))
      } catch (error) { refuse(error) }
      const observed = await ready
      if (!observed && this.pressureAvailability === 'supported') this.detach()
      return observed && !stop.aborted
    } catch (error) {
      // Constructor failure never reaches the observe() rejection path.
      if (capabilityRejection(error)) {
        this.detach()
        this.pressureAvailability = 'unavailable'
        return !this.pressureRestricted && !stop.aborted
      }
      this.pressureAvailability = 'supported'
      this.detach()
      return false
    }
    finally { if (timer) clearTimeout(timer); stop.removeEventListener('abort', aborted) }
  }
  close(): void { this.detach() }
  private detach(): void {
    this.generation++
    this.observer?.disconnect()
    this.observer = undefined
    this.pressure = null
    this.observedAt = -Infinity
  }
  private pressureLimited(): boolean {
    if (this.pressure === 'nominal' && freshPressure(this.observedAt)) return false
    if (this.pressureRestricted || this.pressureAvailability !== 'unavailable') return true
    return false
  }
  private stickyConnection(refused: boolean): { metered: boolean; slow: boolean; refused: boolean } {
    return {
      metered: this.saveDataRestricted || this.cellularRestricted,
      slow: this.slowLinkRestricted,
      refused,
    }
  }
  private connectionLimited(): { metered: boolean; slow: boolean; refused: boolean } {
    let connection: Connection | null | undefined
    try { connection = this.connection() ?? null }
    catch { return this.stickyConnection(true) }
    if (connection == null) return this.stickyConnection(false)
    if (typeof connection !== 'object') return this.stickyConnection(true)
    const link: Connection = connection
    const read = (field: 'saveData' | 'type' | 'effectiveType'): { value: unknown; refused: boolean } => {
      try { return { value: link[field], refused: false } }
      catch { return { value: undefined, refused: true } }
    }
    const saveData = read('saveData'), type = read('type'), effectiveType = read('effectiveType')
    let refused = saveData.refused || type.refused || effectiveType.refused
    if (!saveData.refused) {
      if (saveData.value === true) this.saveDataRestricted = true
      else if (saveData.value === false) this.saveDataRestricted = false
      else if (saveData.value !== undefined) refused = true
    }
    if (!type.refused) {
      if (type.value === 'cellular') this.cellularRestricted = true
      else if (type.value === 'bluetooth' || type.value === 'ethernet' ||
               type.value === 'wifi' || type.value === 'wimax') this.cellularRestricted = false
      // Unknown/mixed/other connections cannot clear a known cellular path.
      // A disconnected or malformed observation cannot authorize sending.
      else if (type.value !== undefined && type.value !== 'unknown' &&
               type.value !== 'mixed' && type.value !== 'other') refused = true
    }
    if (!effectiveType.refused) {
      const kind = effectiveType.value
      if (kind === 'slow-2g' || kind === '2g') this.slowLinkRestricted = true
      else if (kind === '3g' || kind === '4g') this.slowLinkRestricted = false
      else if (kind !== undefined) refused = true
    }
    return this.stickyConnection(refused)
  }
  private heapLimited(): boolean {
    let memory: HeapMemory | null | undefined
    try { memory = (performance as Performance & { memory?: HeapMemory | null }).memory }
    catch { return true }
    if (memory == null) return this.heapRestricted
    if (typeof memory !== 'object') return true
    let used: unknown, limit: unknown
    try { used = memory.usedJSHeapSize; limit = memory.jsHeapSizeLimit }
    catch { return true }
    if (typeof used !== 'number' || typeof limit !== 'number' || !Number.isFinite(used) || !Number.isFinite(limit) ||
        used < 0 || limit <= 0) return true
    if (used / limit >= 0.8) { this.heapRestricted = true; return true }
    this.heapRestricted = false
    return false
  }
}
