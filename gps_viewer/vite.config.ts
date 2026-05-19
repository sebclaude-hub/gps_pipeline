import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Im Dev-Modus: /data/* an view.py-Server weiterleiten
    proxy: {
      '/data': 'http://localhost:8765',
    },
  },
  build: {
    // Große Bundles (deck.gl) brauchen etwas mehr Platz
    chunkSizeWarningLimit: 2000,
  },
})
