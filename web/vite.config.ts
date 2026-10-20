import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The backend runs on :8000; /api/* is forwarded there so the browser never needs CORS.
const API_URL = process.env.API_URL ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: API_URL, changeOrigin: true, rewrite: (p) => p.replace(/^\/api/, '') },
    },
  },
})
