import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  test: {
    // jsdom 27's @asamuzakjp/css-color dependency requires an ESM-only
    // @csstools/css-calc build via require(), which crashes under both the
    // "forks" and "threads" vitest pools on this machine's Node 20.18 (same
    // class of toolchain mismatch as the Vite 8 rolldown issue documented
    // in docs/architecture.md). happy-dom is a free, actively-maintained
    // alternative DOM implementation with no such dependency chain.
    environment: 'happy-dom',
    globals: true,
    setupFiles: ['./src/test/setup.js'],
  },
})
