import { existsSync, statSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawnSync } from 'node:child_process'
import { verifyBranding } from '../../branding/verify.mjs'
import { verifyNativeResources } from './native-resources.mjs'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)
const root = resolve(__dirname, '..', '..', '..')

const required = [
  ...['disclosure', 'catalog', 'desktop-origins'].map(name => ({
    label: `product telemetry ${name}`, path: join(root, 'studio/electron/dist', `telemetry-${name}.json`),
  })),
  ...(process.platform === 'win32' ? [{
    label: 'native Windows telemetry privacy guard', path: join(root, 'studio/electron/dist/telemetry-private-store.exe'),
  }] : []),
  { label: 'project license', path: join(root, 'build-tmp', 'notices', 'LICENSE') },
  { label: 'third-party license inventory', path: join(root, 'build-tmp', 'notices', 'inventory.json') },
  { label: 'software bill of materials', path: join(root, 'build-tmp', 'notices', 'sbom.cdx.json') },
  {
    label: 'frontend index',
    path: join(root, 'studio', 'frontend', 'dist-desktop', 'index.html'),
  },
  {
    label: 'frontend assets',
    path: join(root, 'studio', 'frontend', 'dist-desktop', 'assets'),
    directory: true,
  },
  {
    label: 'local vault client',
    path: join(root, 'dist-client', 'mnemion-client', process.platform === 'win32' ? 'mnemion-client.exe' : 'mnemion-client'),
  },
]

const missing = required.filter(item => {
  if (!existsSync(item.path)) return true
  const stat = statSync(item.path)
  return item.directory ? !stat.isDirectory() : !stat.isFile()
})

if (missing.length > 0) {
  console.error('Missing required packaged resources:')
  for (const item of missing) {
    console.error(`- ${item.label}: ${item.path}`)
  }
  console.error('Run npm run build:resources before packaging.')
  process.exit(1)
}

verifyBranding(join(root, 'studio', 'frontend', 'dist-desktop'))
verifyNativeResources(join(root, 'build-tmp/native-resources'))
const python = process.env.MNEMION_BUILD_PYTHON || resolve(root, 'studio/client/.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')
const scan = spawnSync(python, ['-m', 'deploy.secret_scan', '--paths',
  resolve(root, 'studio/electron/dist'), resolve(root, 'studio/frontend/dist-desktop'),
  '--output', resolve(root, 'output/desktop-secret-scan.json')], { cwd: root, stdio: 'inherit' })
if (scan.status !== 0) process.exit(scan.status || 1)
console.log('Packaged resources and Mnemion brand assets verified.')
