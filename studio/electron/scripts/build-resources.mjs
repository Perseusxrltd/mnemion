import { spawnSync } from 'node:child_process'
import { existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, renameSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../../..')
function run(command, args) {
  const result = spawnSync(command, args, { cwd: root, stdio: 'inherit' })
  if (result.status !== 0) process.exit(result.status || 1)
}
if (!process.env.npm_execpath) throw new Error('Run this build through npm')
run(process.execPath, [process.env.npm_execpath, '--prefix', resolve(root, 'packages/client'), 'run', 'build'])
run(process.execPath, [process.env.npm_execpath, '--prefix', resolve(root, 'studio/frontend'), 'run', 'build:electron'])
const python = process.env.MNEMION_BUILD_PYTHON || resolve(root, 'studio/client/.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')
if (!existsSync(python)) throw new Error('Run uv sync --project studio/client --locked or set MNEMION_BUILD_PYTHON')
const probe = spawnSync(python, ['-c', 'import json,platform,sys; print(json.dumps({"arch":platform.machine().lower(),"platform":sys.platform}))'], { encoding: 'utf8' })
if (probe.status !== 0) throw new Error('The build Python could not be started')
const host = JSON.parse(probe.stdout)
const expected = process.arch === 'x64' ? ['x86_64', 'amd64'] : ['arm64', 'aarch64']
if (host.platform !== process.platform || !expected.includes(host.arch)) {
  throw new Error('Build on the target operating system with Python and Node of the same architecture')
}
run(python, ['-m', 'PyInstaller', '--name', 'mnemion-client', '--onedir', '--noconfirm', '--clean', '--noupx',
  '--paths', root, '--distpath', resolve(root, 'dist-client'), '--workpath', resolve(root, 'build-tmp/client'),
  '--specpath', resolve(root, 'build-tmp'), '--exclude-module', 'chromadb', '--exclude-module', 'fastembed',
  '--exclude-module', 'onnxruntime', '--exclude-module', 'torch', '--exclude-module', 'pytest',
  resolve(root, 'studio/bridge/main.py')])
if (process.platform === 'darwin') run(python, ['-m', 'deploy.macos_sparkle', 'build'])
run(python, [resolve(root, 'deploy/notices.py'), '--root', root, '--python',
  '--analysis', resolve(root, 'build-tmp/client/mnemion-client/Analysis-00.toc'),
  '--frontend', resolve(root, 'studio/frontend'), '--electron', resolve(root, 'studio/electron'), '--output', resolve(root, 'build-tmp/notices'),
  ...(process.platform === 'darwin' ? ['--sparkle', resolve(root, 'build-tmp/macos-update/sparkle')] : [])])

// Build the full service with the repository lock, separately from the small
// vault client. No Python or database installation is required on the user's PC.
const enginePython = process.env.MNEMION_ENGINE_PYTHON || resolve(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')
if (!existsSync(enginePython)) throw new Error('Run uv sync --locked --no-default-groups --group native-build with native Python 3.13, or set MNEMION_ENGINE_PYTHON')
const engineArch = process.platform === 'win32' ? 'x64' : process.arch
const engineProbe = spawnSync(enginePython, ['-c', 'import json,platform,sys,sysconfig; arch=sysconfig.get_platform() if sys.platform=="win32" else platform.machine().lower(); print(json.dumps({"arch":arch,"platform":sys.platform}))'], { encoding: 'utf8' })
if (engineProbe.status !== 0) throw new Error('The engine build Python could not be started')
const engineHost = JSON.parse(engineProbe.stdout)
const expectedEngine = process.platform === 'win32' ? ['win-amd64'] : expected
if (engineHost.platform !== process.platform || !expectedEngine.includes(engineHost.arch)) throw new Error('The service Python must match the backend target: x64 on Windows, native on Linux/macOS')
const databaseDirectory = resolve(root, process.env.MNEMION_POSTGRES_ARCHIVES || 'build-tmp/native-postgres')
const platform = { linux: 'linux', darwin: 'macos', win32: 'windows' }[process.platform]
const databaseArch = process.platform === 'win32' ? 'x64' : process.arch
const databaseArchives = readdirSync(databaseDirectory).filter(name => name.endsWith(`-${platform}-${databaseArch}.zip`))
if (databaseArchives.length !== 1) throw new Error('Supply exactly one verified native PostgreSQL archive for this target')
mkdirSync(resolve(root, 'build-tmp'), { recursive: true })
const work = mkdtempSync(resolve(root, 'build-tmp/desktop-native-'))
const version = JSON.parse(readFileSync(resolve(root, 'studio/electron/package.json'), 'utf8')).version
const engineName = `mnemion-engine-${version}-${platform}-${engineArch}.zip`
let engineArchive
if (process.env.MNEMION_ENGINE_ARCHIVES) {
  const directory = resolve(root, process.env.MNEMION_ENGINE_ARCHIVES)
  const archives = readdirSync(directory).filter(name => name.endsWith('.zip'))
  if (archives.length !== 1 || archives[0] !== engineName) throw new Error('Supply exactly one matching native service archive for this target')
  engineArchive = resolve(directory, engineName)
} else {
  if (process.platform === 'win32' && process.arch === 'arm64') throw new Error('Build the x64 backend on Windows x64 and supply MNEMION_ENGINE_ARCHIVES for the native ARM desktop')
  run(enginePython, ['-m', 'deploy.build_native_engine', '--work', resolve(work, 'work'), '--output', resolve(work, 'output')])
  engineArchive = resolve(work, 'output', engineName)
}
// Assembly verifies source and lock hashes, version, licenses and every binary's
// architecture for imported archives exactly as it does for a local build.
run(enginePython, ['-m', 'deploy.native_resources', '--resources', resolve(work, 'resources'), '--platform', platform, '--arch', process.arch, '--version', version,
  '--engine-archive', engineArchive,
  '--database-archive', resolve(databaseDirectory, databaseArchives[0])])
const resources = resolve(root, 'build-tmp/native-resources')
rmSync(resources, { recursive: true, force: true })
renameSync(resolve(work, 'resources'), resources)
rmSync(work, { recursive: true, force: true })
