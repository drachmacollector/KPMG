/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'bg-deep':     '#080d18',
        'bg-base':     '#0e1624',
        'bg-surface':  '#151f32',
        'bg-elevated': '#1c2a42',
        'bg-card':     '#131d2e',
        'accent':      '#6366f1',
        'accent-hover':'#818cf8',
        'accent-press':'#4f46e5',
        'accent-muted':'#3730a3',
        'success':     '#22c55e',
        'error':       '#ef4444',
        'text-primary': '#f1f5f9',
        'text-secondary':'#94a3b8',
        'text-muted':  '#475569',
        'text-accent': '#a5b4fc',
        'border-col':  '#1e2d45',
        'border-focus':'#6366f1',
      },
      fontFamily: {
        sans: ['Inter', 'Segoe UI', 'sans-serif'],
        mono: ['Cascadia Code', 'Cascadia Mono', 'Consolas', 'monospace'],
      },
      animation: {
        'fade-in': 'fadeIn 0.7s cubic-bezier(0.16, 1, 0.3, 1) forwards',
        'slide-up': 'slideUp 0.5s cubic-bezier(0.16, 1, 0.3, 1) forwards',
        'pulse-glow': 'pulseGlow 2s ease-in-out infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0', transform: 'translateY(12px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(20px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        pulseGlow: {
          '0%, 100%': { boxShadow: '0 0 20px rgba(99,102,241,0.4)' },
          '50%': { boxShadow: '0 0 40px rgba(99,102,241,0.7)' },
        },
      },
    },
  },
  plugins: [],
}
