/** Compile the actual UI owner outside the measured desktop process. */
import { readFileSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { pathToFileURL, fileURLToPath } from 'node:url'
import ts from 'typescript'

const repository = fileURLToPath(new URL('../../../', import.meta.url))
const destination = process.argv[2]
if (!destination?.includes('mnemion-owned-pipeline-')) throw new Error('Isolated diagnostic output required')
const source = resolve(repository, 'studio/frontend/src/workspace/measured-client.ts')
const code = ts.transpileModule(readFileSync(source, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true },
}).outputText
const url = path => JSON.stringify(pathToFileURL(resolve(repository, path)).href)
const data = path => readFileSync(resolve(repository, path), 'utf8')
// The supplied native store and surface are mandatory here. These unused
// browser defaults throw so the diagnostic cannot accidentally substitute a
// browser policy or claim that it exercised the renderer/IPC boundary.
writeFileSync(destination, `
import * as sdk from ${url('packages/client/dist/index.js')};
import { TelemetryWorkflow } from ${url('studio/electron/dist/telemetry-workflow.js')};
const controls = ${data('mnemion/product_telemetry/control-origins.json')};
const methods = ${data('mnemion/product_telemetry/studio-methods.json')};
const exports = {};
function require(name) {
  if (name === '@mnemion/client') return sdk;
  if (name.endsWith('/control-origins.json')) return controls;
  if (name.endsWith('/studio-methods.json')) return methods;
  if (name.endsWith('/telemetry-workflow')) return { TelemetryWorkflow };
  if (name === './telemetry-policy') return {
    get productWorkflowStore() { throw new Error('Supply the real native store'); },
    telemetrySurface() { throw new Error('Supply the actual surface'); },
  };
  throw new Error('Unreviewed diagnostic import');
}
${code}
const fixtureMeasuredStudioClient = exports.measuredStudioClient;
export { fixtureMeasuredStudioClient as measuredStudioClient };
export const MnemionClient = sdk.MnemionClient;
`, { flag: 'wx', mode: 0o600 })
