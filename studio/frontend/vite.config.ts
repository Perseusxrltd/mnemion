import { defineConfig, searchForWorkspaceRoot } from 'vite'
import react from '@vitejs/plugin-react'
import tailwind from '@tailwindcss/vite'
import { fileURLToPath } from 'node:url'
import { existsSync, readFileSync } from 'node:fs'

const root = fileURLToPath(new URL('.', import.meta.url))
const version = JSON.parse(readFileSync(new URL('package.json', import.meta.url), 'utf8')).version
for (const document of ['README.md', 'SECURITY.md', 'CONTRIBUTING.md', 'studio/README.md',
  'docs/ROADMAP.md', 'docs/service/README.md', 'docs/service/updates.md', `docs/releases/${version}.md`]) {
  if (!existsSync(new URL(`../../${document}`, import.meta.url))) {
    throw new Error(`Studio requires its offline documentation: ${document}`)
  }
}

export default defineConfig({
  root,
  plugins: [react(), tailwind()],
  // Relative base so Electron can load bundled assets from file://.
  base: process.env.ELECTRON_BUILD ? './' : '/',
  server: {
    port: 5173,
    fs: {
      // Lazy help imports live beside the frontend, outside its npm workspace.
      // Allow the public documentation without exposing the whole checkout.
      allow: [searchForWorkspaceRoot(root), ...[
        'docs', 'README.md', 'SECURITY.md', 'CONTRIBUTING.md', 'studio/README.md',
      ].flatMap(path => {
        const file = fileURLToPath(new URL(`../../${path}`, import.meta.url))
        // Vite checks both the clean filename and the raw module identifier.
        return path.endsWith('.md') ? [file, `${file}?raw`] : [file]
      })],
    },
    proxy: {
      '/api': { target: 'http://127.0.0.1:7891', changeOrigin: true },
      '/v1': { target: 'http://127.0.0.1:7892', changeOrigin: true },
      '/health': { target: 'http://127.0.0.1:7892', changeOrigin: true },
    },
  },
  build: {
    outDir: process.env.ELECTRON_BUILD ? 'dist-desktop' : 'dist',
  },
})
