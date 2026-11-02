import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// base './' + <base href> injected by the backend => works under any sub-path behind a proxy
export default defineConfig({
  base: './',
  plugins: [react()],
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
})
