/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        base:     '#070b11',
        surface:  '#0d1421',
        elevated: '#141e2f',
        border:   '#1e2f47',
        'border-bright': '#2a4060',
        accent:   '#c9922a',
        'accent-bright': '#f0b445',
        'text-primary':   '#dde4f0',
        'text-secondary': '#8094b4',
        'text-muted':     '#3d5270',
        'active-green':   '#22c55e',
        'error-red':      '#ef4444',
      },
      fontFamily: {
        display: ['Cormorant', 'Georgia', 'serif'],
        body:    ['DM Sans', 'sans-serif'],
        mono:    ['JetBrains Mono', 'monospace'],
      },
      animation: {
        'pulse-slow':  'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'scan':        'scan 8s linear infinite',
        'blink':       'blink 1.2s step-end infinite',
        'shimmer':     'shimmer 2s linear infinite',
        'slide-in':    'slideIn 0.35s cubic-bezier(0.16, 1, 0.3, 1)',
        'fade-up':     'fadeUp 0.4s ease forwards',
      },
      keyframes: {
        scan: {
          '0%':   { backgroundPosition: '0 -100vh' },
          '100%': { backgroundPosition: '0 100vh' },
        },
        blink: {
          '0%, 100%': { opacity: '1' },
          '50%':      { opacity: '0' },
        },
        shimmer: {
          '0%':   { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        slideIn: {
          from: { transform: 'translateX(100%)' },
          to:   { transform: 'translateX(0)' },
        },
        fadeUp: {
          from: { opacity: '0', transform: 'translateY(12px)' },
          to:   { opacity: '1', transform: 'translateY(0)' },
        },
      },
    },
  },
  plugins: [],
}
