import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// CRITICAL: base: './' ensures all assets load via relative paths when
// pywebview serves the built index.html from the local filesystem.
// Without this, Vite defaults to absolute paths (/assets/...) which
// break when the file is opened as file:///path/to/frontend_dist/index.html.
export default defineConfig({
  plugins: [react()],
  base: './',
})
