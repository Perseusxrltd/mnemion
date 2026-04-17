import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:7891', changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    // Relative base so Electron can load from file://
    base: process.env.ELECTRON_BUILD ? './' : '/',
  },
})
