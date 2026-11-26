/** @type {import('tailwindcss').Config} */
// Colours, fonts and animations live as CSS variables / keyframes in
// src/index.css; Tailwind is used for layout and spacing utilities only.
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,jsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'Segoe UI', 'sans-serif'],
        mono: ['Cascadia Code', 'Cascadia Mono', 'Consolas', 'monospace'],
      },
    },
  },
  plugins: [],
}
