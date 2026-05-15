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
        'retry-amber':    '#d97706',
        'retry-amber-bright': '#f59e0b',
      },
      backgroundImage: {
        'quality-grad': 'linear-gradient(90deg, #ef4444 0%, #d97706 35%, #c9922a 60%, #22c55e 100%)',
        'orbit-halo': 'radial-gradient(circle, rgba(201,146,42,0.12) 0%, transparent 70%)',
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
        'spin-slow':   'spin 60s linear infinite',
        'orbit-pulse': 'orbitPulse 2.4s ease-in-out infinite',
        'quake':       'quake 0.5s ease-in-out',
        'token-pop':   'tokenPop 320ms ease-out forwards',
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
        orbitPulse: {
          '0%, 100%': { transform: 'scale(1)',   opacity: '0.9' },
          '50%':      { transform: 'scale(1.4)', opacity: '0.3' },
        },
        quake: {
          '0%, 100%': { transform: 'translate(0, 0) rotate(0)' },
          '20%':      { transform: 'translate(-1px, 1px) rotate(-0.4deg)' },
          '40%':      { transform: 'translate(1px, -1px) rotate(0.4deg)' },
          '60%':      { transform: 'translate(-1px, 0) rotate(-0.2deg)' },
          '80%':      { transform: 'translate(1px, 1px) rotate(0.2deg)' },
        },
        tokenPop: {
          from: { backgroundColor: 'rgba(201,146,42,0.18)' },
          to:   { backgroundColor: 'transparent' },
        },
      },
    },
  },
  plugins: [],
}
