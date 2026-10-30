/** An unavailable or timed-out check suppresses telemetry; it never repairs ACLs. */
import { spawn, type ChildProcess } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { deliveryObservationEnabled, noteAcl } from './telemetry-observation-diagnostic.mjs'

export function windowsTelemetryPrivateExecutable(moduleUrl = import.meta.url): string {
  // spawn cannot execute an entry inside ASAR. Packaging explicitly keeps this
  // one native binary beside the archive; source runs use their ordinary dist.
  return fileURLToPath(new URL('./telemetry-private-store.exe', moduleUrl))
    .replace(/([\\/])app\.asar([\\/])/, '$1app.asar.unpacked$2')
}

/** One live helper, including the interval between a kill request and OS exit.
 * A deadline is a refusal, never proof that the old process has been reaped. */
export class WindowsTelemetryPrivateProbe {
  private child?: ChildProcess
  constructor(private readonly launch: (root: string, database: string) => ChildProcess = (root, database) =>
    spawn(windowsTelemetryPrivateExecutable(), [root, database], {
      stdio: 'ignore', windowsHide: true, shell: false,
    })) {}

  read(root: string, database: string): Promise<boolean> {
    const diagnose = deliveryObservationEnabled()
    if (this.child) {
      if (diagnose) noteAcl('refused', 0)
      return Promise.resolve(false)
    }
    const started = diagnose ? performance.now() : 0
    return new Promise(resolve => {
      let done = false, timer: ReturnType<typeof setTimeout> | undefined
      const finish = (accepted: boolean, outcome: 'accepted' | 'refused' | 'timed_out' = accepted ? 'accepted' : 'refused') => {
        if (!done) {
          done = true
          clearTimeout(timer)
          if (diagnose) noteAcl(outcome, performance.now() - started)
          resolve(accepted)
        }
      }
      let child: ChildProcess
      try { child = this.launch(root, database) } catch { finish(false, 'refused'); return }
      this.child = child
      const reaped = () => { if (this.child === child) this.child = undefined }
      child.on('error', () => {
        // A spawn error has no process. A kill error with a live PID does not
        // release ownership or permit another helper to accumulate behind it.
        if (child.pid === undefined) reaped()
        else child.unref()
        finish(false, 'refused')
      })
      child.once('exit', code => { reaped(); finish(code === 0) })
      timer = setTimeout(() => {
        try { child.kill() } catch { /* Keep ownership until actual exit. */ }
        child.unref()
        finish(false, 'timed_out')
      }, 1000)
      timer.unref()
    })
  }
}

const privateProbe = new WindowsTelemetryPrivateProbe()

export function windowsTelemetryPrivateStore(root: string, database: string): Promise<boolean> {
  return privateProbe.read(root, database)
}
