import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Backend target: inside Docker this is the `backend` service; locally it's
// http://localhost:8000. Overridable via VITE_BACKEND_URL.
const backend = process.env.VITE_BACKEND_URL || 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/api': { target: backend, changeOrigin: true },
      '/health': { target: backend, changeOrigin: true },
      '/ws': { target: backend, ws: true, changeOrigin: true },
    },
  },
  preview: {
    host: true,
    port: 5173,
  },
})
