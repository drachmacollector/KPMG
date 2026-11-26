import { readFileSync } from 'node:fs'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const pkg = JSON.parse(readFileSync(new URL('./package.json', import.meta.url), 'utf-8'))

// base: './' — assets load via relative paths when pywebview opens the built
// index.html from the local filesystem (file://).
// outDir: '../frontend_dist' — exactly the folder PyInstaller bundles
// (packaging/mahabocw_gui.spec), so a build can never ship a stale UI.
export default defineConfig({
  plugins: [react()],
  base: './',
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
  },
  build: {
    outDir: '../frontend_dist',
    emptyOutDir: true,
  },
})
