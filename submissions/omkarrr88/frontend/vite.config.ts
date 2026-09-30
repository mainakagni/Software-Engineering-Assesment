/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In development the API runs separately on port 8000. In production the backend serves this
// build from the same origin, so the paths are the same in both.
const API = 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': API,
      '/docs': API,
      '/openapi.json': API,
      '/health': API,
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
  },
})
