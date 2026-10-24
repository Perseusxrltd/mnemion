/** Bounded current browser capability checks; no guesses about a Wi-Fi tariff. */
type Connection = EventTarget & { saveData?: boolean; type?: string; effectiveType?: string }
type PressureRecord = { state: string }
type PressureObserverLike = { observe: (source: 'cpu', options: { sampleInterval: number }) => Promise<void>; disconnect: () => void }
type PressureConstructor = new (callback: (records: PressureRecord[]) => void) => PressureObserverLike
export type BrowserTelemetryConditions = { network: 'unknown' | 'metered' | 'unmetered'; constrained: boolean }

export class BrowserConditions {
  private pressure: string | null = null
  private observedAt = -Infinity
  private observer?: PressureObserverLike
  private generation = 0

  connection(): Connection | undefined {
    return (navigator as Navigator & { connection?: Connection }).connection
  }
  read(): BrowserTelemetryConditions {
    try {
      const connection = this.connection()
      const heap = (performance as Performance & { memory?: { usedJSHeapSize: number; jsHeapSizeLimit: number } }).memory
      // Data-saving mode and a cellular connection are treated conservatively.
      // Ethernet/Wi-Fi and saveData=false never imply an unmetered plan.
      const metered = connection?.saveData === true || connection?.type === 'cellular'
      return { network: metered ? 'metered' : 'unknown', constrained:
        navigator.onLine !== true || document.visibilityState !== 'visible' || metered ||
        ['slow-2g', '2g'].includes(connection?.effectiveType ?? '') ||
        this.pressure !== 'nominal' || performance.now() - this.observedAt > 2000 ||
        !heap || !Number.isFinite(heap.usedJSHeapSize) || !Number.isFinite(heap.jsHeapSizeLimit) ||
        heap.usedJSHeapSize < 0 || heap.jsHeapSizeLimit <= 0 || heap.usedJSHeapSize / heap.jsHeapSizeLimit >= 0.8 }
    } catch { return { network: 'unknown', constrained: true } }
  }
  async start(stop: AbortSignal): Promise<boolean> {
    this.close()
    const Constructor = (globalThis as typeof globalThis & { PressureObserver?: PressureConstructor }).PressureObserver
    if (!Constructor || stop.aborted) return false
    const generation = this.generation
    let timer: ReturnType<typeof setTimeout> | undefined, finish = (_value: boolean) => {}
    const ready = new Promise<boolean>(resolve => { finish = resolve })
    const aborted = () => { this.close(); finish(false) }
    try {
      this.observer = new Constructor(records => {
        if (generation !== this.generation || stop.aborted || !records.length) return
        this.pressure = records[records.length - 1].state
        this.observedAt = performance.now()
        finish(this.pressure === 'nominal')
      })
      stop.addEventListener('abort', aborted, { once: true })
      // Only during newly offered awake work, never a periodic/idle observer.
      timer = setTimeout(() => { this.close(); finish(false) }, 1000)
      void this.observer.observe('cpu', { sampleInterval: 250 }).catch(() => {
        if (generation === this.generation) this.close()
        finish(false)
      })
      const observed = await ready
      if (!observed) this.close()
      return observed && !stop.aborted
    } catch { this.close(); return false }
    finally { if (timer) clearTimeout(timer); stop.removeEventListener('abort', aborted) }
  }
  close(): void {
    this.generation++
    this.observer?.disconnect(); this.observer = undefined
    this.pressure = null; this.observedAt = -Infinity
  }
}
