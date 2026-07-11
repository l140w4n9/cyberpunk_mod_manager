import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

const backendPort = (() => {
  const env = process.env.CP2077_PORT?.trim()
  if (env && /^\d+$/.test(env)) return Number(env)
  return 8000
})()

export default defineConfig({
  plugins: [vue()],
  base: '/',
  build: {
    outDir: resolve(__dirname, '../src/cyberpunk_mod_manager/web'),
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: `http://127.0.0.1:${backendPort}`,
        changeOrigin: true,
      },
    },
  },
})
