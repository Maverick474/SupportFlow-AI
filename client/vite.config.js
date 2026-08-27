import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const backendTarget = process.env.BACKEND_TARGET || 'http://localhost:8000'
const proxy = {
  '/api': {
    target: backendTarget,
    changeOrigin: true,
  },
  '/health': {
    target: backendTarget,
    changeOrigin: true,
  },
}

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy,
  },
  preview: {
    host: '0.0.0.0',
    port: 4173,
    proxy,
  },
})
