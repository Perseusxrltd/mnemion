import { spawnSync } from 'node:child_process'
import { join } from 'node:path'
import { root, platformArtifacts } from './platform-artifacts.mjs'

const artifacts = platformArtifacts()
const python = process.env.MNEMION_BUILD_PYTHON || join(root, process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python')
const client = join(artifacts.resources, 'client', process.platform === 'win32' ? 'mnemion-client.exe' : 'mnemion-client')
const result = spawnSync(python, ['-m', 'pytest', 'client_tests/test_packaged_client.py', '-q'], {
  cwd: root, stdio: 'inherit', env: { ...process.env, MNEMION_PACKAGED_CLIENT: client },
})
if (result.error) throw result.error
process.exit(result.status ?? 1)
