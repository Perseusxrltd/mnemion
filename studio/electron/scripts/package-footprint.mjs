/** Logical installed bytes, without following framework links or reading contents. */
import { readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

export function packageFootprint(bundle, resources) {
  const prefix = relative(bundle, resources).replaceAll('\\', '/') + '/'
  const components = new Map()
  let files = 0, bytes = 0
  const pending = [bundle]
  while (pending.length) {
    const directory = pending.pop()
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const path = join(directory, entry.name)
      if (entry.isDirectory()) pending.push(path)
      else if (entry.isFile()) {
        const size = statSync(path).size, name = relative(bundle, path).replaceAll('\\', '/')
        const group = name.startsWith(prefix) ? 'resources/' + name.slice(prefix.length).split('/')[0] : 'application'
        files++; bytes += size
        components.set(group, (components.get(group) ?? 0) + size)
      }
    }
  }
  return { regular_file_bytes: bytes, files, components: [...components.entries()]
    .sort((a, b) => b[1] - a[1]).map(([component, bytes]) => ({ component, bytes })) }
}
