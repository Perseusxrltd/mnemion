/** An unavailable or timed-out check suppresses telemetry; it never repairs ACLs. */
import { spawn, type ChildProcess } from 'node:child_process'
import { fileURLToPath } from 'node:url'

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
    if (this.child) return Promise.resolve(false)
    return new Promise(resolve => {
      let done = false, timer: ReturnType<typeof setTimeout> | undefined
      const finish = (accepted: boolean) => { if (!done) { done = true; clearTimeout(timer); resolve(accepted) } }
      let child: ChildProcess
      try { child = this.launch(root, database) } catch { finish(false); return }
      this.child = child
      const reaped = () => { if (this.child === child) this.child = undefined }
      child.on('error', () => {
        // A spawn error has no process. A kill error with a live PID does not
        // release ownership or permit another helper to accumulate behind it.
        if (child.pid === undefined) reaped()
        else child.unref()
        finish(false)
      })
      child.once('exit', code => { reaped(); finish(code === 0) })
      timer = setTimeout(() => {
        try { child.kill() } catch { /* Keep ownership until actual exit. */ }
        child.unref()
        finish(false)
      }, 1000)
      timer.unref()
    })
  }
}

const privateProbe = new WindowsTelemetryPrivateProbe()

export function windowsTelemetryPrivateStore(root: string, database: string): Promise<boolean> {
  return privateProbe.read(root, database)
}
