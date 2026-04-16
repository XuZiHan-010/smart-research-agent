import { motion } from 'framer-motion'

export function EmptyState() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: 0.1 }}
      className="flex flex-col items-center justify-center h-full text-center px-8 select-none"
    >
      {/* Decorative emblem */}
      <div className="relative mb-10">
        <div className="w-24 h-24 rounded-full border border-border flex items-center justify-center relative">
          <div className="absolute inset-0 rounded-full border border-accent opacity-20 animate-pulse-slow" />
          <div className="absolute inset-3 rounded-full border border-dashed border-border" />
          <span className="text-3xl">🔍</span>
        </div>
        {/* Corner ticks */}
        {['-top-1 -left-1', '-top-1 -right-1', '-bottom-1 -left-1', '-bottom-1 -right-1'].map((pos, i) => (
          <span key={i} className={`absolute ${pos} w-2 h-2 border-accent opacity-50`}
            style={{ borderWidth: '1px 0 0 1px', transform: i > 1 ? `rotate(${(i - 1) * 90}deg)` : `rotate(${i * -90}deg)` }}
          />
        ))}
      </div>

      <h2 className="font-display text-3xl font-light text-text-primary tracking-wide mb-3">
        Intelligence Briefing System
      </h2>
      <p className="text-text-secondary text-sm max-w-sm leading-relaxed mb-10">
        Enter a company name, select your research dimensions, and receive a comprehensive analyst-grade report.
      </p>

      {/* How it works */}
      <div className="grid grid-cols-3 gap-px bg-border w-full max-w-lg border border-border">
        {[
          { step: '01', label: 'Configure', desc: 'Select dimensions & depth' },
          { step: '02', label: 'Research',  desc: '6 parallel AI agents' },
          { step: '03', label: 'Report',    desc: 'MD · PDF · JSON output' },
        ].map(({ step, label, desc }) => (
          <div key={step} className="bg-surface p-4 text-left">
            <div className="font-mono text-xs text-accent mb-2 tracking-widest">{step}</div>
            <div className="text-text-primary text-sm font-medium mb-1">{label}</div>
            <div className="text-text-muted text-xs">{desc}</div>
          </div>
        ))}
      </div>

      <p className="mt-8 font-mono text-xs text-text-muted tracking-widest uppercase">
        — System Ready —
      </p>
    </motion.div>
  )
}
