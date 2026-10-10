import { spawnSync } from 'node:child_process'
import { existsSync } from 'node:fs'
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
