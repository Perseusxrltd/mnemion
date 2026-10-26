import { copyFileSync, readdirSync, rmSync } from 'node:fs'
import { join } from 'node:path'
import { telemetryResourceNames, telemetryWireResource } from '../dist/telemetry-resources.js'

export function telemetryResourceEntries(destination) {
  return telemetryResourceNames.map(name => ({
    label: `product telemetry ${name}`, path: join(destination, `telemetry-${name}.json`),
  }))
}

export function copyTelemetryResources(source, destination) {
  for (const name of telemetryResourceNames) {
    copyFileSync(join(source, `${name}.json`), join(destination, `telemetry-${name}.json`))
  }
  // Incremental builds must not conceal a missing active format or package a
  // retired format left in dist by an earlier release.
  for (const name of readdirSync(destination)) {
    if (/^telemetry-wire-v\d+\.json$/.test(name) && name !== telemetryWireResource) {
      rmSync(join(destination, name))
    }
  }
}
