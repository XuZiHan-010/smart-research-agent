import { useState, useEffect } from 'react'

export function LandscapePrompt() {
  const [visible, setVisible] = useState(() =>
    window.matchMedia('(orientation: portrait) and (max-width: 1024px)').matches
  )

  useEffect(() => {
    const mql = window.matchMedia('(orientation: portrait) and (max-width: 1024px)')
    const handler = (e: MediaQueryListEvent) => setVisible(e.matches)
    mql.addEventListener('change', handler)
    return () => mql.removeEventListener('change', handler)
  }, [])

  if (!visible) return null

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        backgroundColor: '#0a0e17',
        backgroundImage:
          'radial-gradient(circle, rgba(255,255,255,0.04) 1px, transparent 1px)',
        backgroundSize: '24px 24px',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '24px',
        padding: '32px',
      }}
    >
      {/* Animated rotate icon */}
      <svg
        width="72"
        height="72"
        viewBox="0 0 24 24"
        fill="none"
        stroke="#c9922a"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        style={{ animation: 'landscape-rock 1.6s ease-in-out infinite' }}
      >
        {/* Phone outline */}
        <rect x="7" y="2" width="10" height="18" rx="2" />
        {/* Rotate arrows */}
        <path d="M3 9a9 9 0 0 1 9-6" />
        <polyline points="1 9 3 9 3 7" />
        <path d="M21 15a9 9 0 0 1-9 6" />
        <polyline points="23 15 21 15 21 17" />
      </svg>

      <div style={{ textAlign: 'center' }}>
        <p
          style={{
            fontFamily: "'Cormorant', serif",
            fontSize: '2rem',
            fontWeight: 600,
            letterSpacing: '0.2em',
            color: '#c9922a',
            textTransform: 'uppercase',
            margin: '0 0 10px',
          }}
        >
          Rotate Device
        </p>
        <p
          style={{
            fontFamily: "'DM Sans', sans-serif",
            fontSize: '0.875rem',
            color: 'rgba(255,255,255,0.45)',
            letterSpacing: '0.05em',
            margin: 0,
          }}
        >
          This interface is optimized for landscape view
        </p>
      </div>

      <style>{`
        @keyframes landscape-rock {
          0%, 100% { transform: rotate(0deg); }
          25%       { transform: rotate(25deg); }
          75%       { transform: rotate(-10deg); }
        }
      `}</style>
    </div>
  )
}
