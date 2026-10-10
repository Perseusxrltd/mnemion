import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwind from '@tailwindcss/vite'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('.', import.meta.url))

export default defineConfig({
  root,
  plugins: [react(), tailwind()],
  // Relative base so Electron can load bundled assets from file://.
  base: process.env.ELECTRON_BUILD ? './' : '/',
  server: {
    port: 5173,
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
