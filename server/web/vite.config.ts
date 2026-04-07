import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/compose': 'http://localhost:8900',
      '/status': 'http://localhost:8900',
      '/result': 'http://localhost:8900',
      '/confirm': 'http://localhost:8900',
      '/cancel': 'http://localhost:8900',
      '/sessions': 'http://localhost:8900',
      '/api': 'http://localhost:8900',
      '/docs': 'http://localhost:8900',
      '/redoc': 'http://localhost:8900',
      '/openapi.json': 'http://localhost:8900',
    },
  },
})
