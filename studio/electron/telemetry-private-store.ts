/** An unavailable or timed-out check suppresses telemetry; it never repairs ACLs. */
import { spawn } from 'node:child_process'
import { fileURLToPath } from 'node:url'

export function windowsTelemetryPrivateExecutable(moduleUrl = import.meta.url): string {
  // spawn cannot execute an entry inside ASAR. Packaging explicitly keeps this
  // one native binary beside the archive; source runs use their ordinary dist.
  return fileURLToPath(new URL('./telemetry-private-store.exe', moduleUrl))
    .replace(/([\\/])app\.asar([\\/])/, '$1app.asar.unpacked$2')
}

export function windowsTelemetryPrivateStore(root: string, database: string): Promise<boolean> {
  return new Promise(resolve => {
    let done = false
    const finish = (accepted: boolean) => { if (!done) { done = true; clearTimeout(timer); resolve(accepted) } }
    const child = spawn(windowsTelemetryPrivateExecutable(), [root, database], {
      stdio: 'ignore', windowsHide: true, shell: false,
    })
    const timer = setTimeout(() => { child.kill(); finish(false) }, 1000)
    timer.unref()
    child.once('error', () => finish(false))
    child.once('exit', code => finish(code === 0))
  })
}
