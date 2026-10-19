/** A slow native installer may keep working, but a stalled or spinning one is bounded. */
export class InstallerProgressWindow {
  constructor(start, { initial = 240_000, stall = 120_000, maximum = 600_000 } = {}) {
    this.start = start
    this.initial = initial
    this.stall = stall
    this.maximum = maximum
    this.lastProgress = start
    this.previous = undefined
  }

  observe(now, processes) {
    if (!Array.isArray(processes)) return
    const snapshot = JSON.stringify(processes.map(item => [item.ProcessId, item.CreationDate,
      item.KernelModeTime, item.UserModeTime, item.ReadTransferCount, item.WriteTransferCount])
      .sort((left, right) => left[0] - right[0]))
    // A first observation is a baseline, not proof that installation progressed.
    if (this.previous !== undefined && this.previous !== snapshot) this.lastProgress = now
    this.previous = snapshot
  }

  expired(now) {
    if (now - this.start >= this.maximum) return 'maximum_duration'
    if (now - this.start >= this.initial && now - this.lastProgress >= this.stall) return 'no_installer_progress'
    return undefined
  }
}
