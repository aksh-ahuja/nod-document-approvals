import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  cacheDir: '../.local/vite',
  server: { proxy: { '/api': process.env.NOD_DEV_API_URL || 'http://127.0.0.1:8000' } },
})
