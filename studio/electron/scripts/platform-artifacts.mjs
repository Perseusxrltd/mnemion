import { readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

export const root = resolve(dirname(fileURLToPath(import.meta.url)), '../../..')
export const packageJson = JSON.parse(readFileSync(join(root, 'studio/electron/package.json'), 'utf8'))

export function platformArtifacts(platform = process.platform, arch = process.arch) {
  if (!['win32', 'darwin', 'linux'].includes(platform) || !['x64', 'arm64'].includes(arch)) {
    throw new Error(`Unsupported desktop build platform: ${platform}/${arch}`)
  }
  const output = join(root, 'dist-electron')
  const product = packageJson.build.productName
  const name = `Mnemion-Studio-${packageJson.version}-${{ win32: 'windows', darwin: 'macos', linux: 'linux' }[platform]}`
  if (platform === 'darwin') {
    const bundle = join(output, arch === 'x64' ? 'mac' : 'mac-arm64', `${product}.app`)
    return { output, bundle, app: join(bundle, 'Contents/MacOS', product), resources: join(bundle, 'Contents/Resources'),
      installers: [join(output, `${name}-${arch}.dmg`), join(output, `${name}-${arch}.zip`)] }
  }
  const unpacked = join(output, `${platform === 'win32' ? 'win' : 'linux'}${arch === 'x64' ? '' : '-arm64'}-unpacked`)
  return { output, bundle: unpacked, app: join(unpacked, platform === 'win32' ? `${product}.exe` : 'mnemion-studio'),
    resources: join(unpacked, 'resources'),
    installers: (platform === 'win32' ? ['exe'] : ['AppImage', 'deb']).map(ext => {
      const artifactArch = platform === 'linux' && arch === 'x64' ? (ext === 'AppImage' ? 'x86_64' : 'amd64') : arch
      return join(output, `${name}-${artifactArch}.${ext}`)
    }) }
}
