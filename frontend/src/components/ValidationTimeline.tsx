import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import clsx from 'clsx'
import { CheckCircle2, RotateCw, ShieldAlert } from 'lucide-react'
import { ValidationSnapshot } from '../types'

interface Props {
  snapshots: ValidationSnapshot[]
  currentIteration: number
}

const DECISION_META: Record<ValidationSnapshot['decision'], {
  icon: typeof CheckCircle2
  cls: string
  label: string
}> = {
  pass:        { icon: CheckCircle2, cls: 'text-active-green border-active-green/40 bg-active-green/10', label: 'Pass' },
  retry:       { icon: RotateCw,     cls: 'text-retry-amber-bright border-retry-amber-bright/40 bg-retry-amber-bright/10', label: 'Retry' },
  force_pass:  { icon: ShieldAlert,  cls: 'text-accent border-accent/40 bg-accent/10', label: 'Force-pass' },
}

export function ValidationTimeline({ snapshots, currentIteration }: Props) {
  const [hoverIdx, setHoverIdx] = useState<number | null>(null)

  return (
    <div className="border-t border-border pt-4">
      <div className="font-mono text-[9px] uppercase tracking-[0.18em] text-text-muted mb-3 flex items-center gap-2">
        <span>Agent Decisions · Validation Loop</span>
        <span className="flex-1 h-px bg-border" />
        <span className="text-accent">{snapshots.length} iter{snapshots.length !== 1 ? 's' : ''}</span>
      </div>

      <div className="relative">
        {/* Timeline track */}
        <div className="absolute left-3 right-3 top-3.5 h-px bg-border" />

        <div className="flex justify-between relative">
          {snapshots.map((snap, i) => {
            const meta = DECISION_META[snap.decision]
            const Icon = meta.icon
            const isCurrent = snap.iteration === currentIteration
            return (
              <div
                key={i}
                className="relative flex flex-col items-center"
                onMouseEnter={() => setHoverIdx(i)}
                onMouseLeave={() => setHoverIdx(null)}
              >
                <motion.div
                  initial={{ scale: 0, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  transition={{ delay: i * 0.06 }}
                  className={clsx(
                    'w-7 h-7 rounded-full border flex items-center justify-center relative z-10 bg-base cursor-pointer',
                    meta.cls,
                    isCurrent && 'ring-2 ring-accent/30 ring-offset-2 ring-offset-base',
                  )}
                >
                  <Icon size={11} />
                </motion.div>

                <div className="mt-2 text-center">
                  <div className="font-mono text-[9px] text-text-muted">
                    iter {String(snap.iteration).padStart(2, '0')}
                  </div>
                  <div className="font-mono text-sm text-text-primary tabular-nums mt-0.5">
                    {snap.overall_score}
                  </div>
                </div>

                {/* Hover detail */}
                <AnimatePresence>
                  {hoverIdx === i && (
                    <motion.div
                      initial={{ opacity: 0, y: 4 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: 4 }}
                      className="absolute top-full mt-2 left-1/2 -translate-x-1/2 w-64 z-20
                                 bg-elevated border border-accent/30 rounded p-3 shadow-2xl"
                    >
                      <div className={clsx('font-mono text-[9px] uppercase tracking-widest mb-2', meta.cls.split(' ')[0])}>
                        {meta.label} · score {snap.overall_score}/100
                      </div>
                      {snap.reason && (
                        <p className="text-text-secondary text-xs leading-relaxed mb-2 italic">
                          "{snap.reason}"
                        </p>
                      )}
                      {snap.flags.length > 0 && (
                        <div className="space-y-1 mb-2">
                          {snap.flags.slice(0, 4).map((f, j) => (
                            <div key={j} className="text-[10px] text-text-muted flex gap-1.5">
                              <span className="text-retry-amber-bright">▸</span>
                              <span>{f}</span>
                            </div>
                          ))}
                        </div>
                      )}
                      {snap.retry_themes.length > 0 && (
                        <div className="pt-2 border-t border-border">
                          <span className="font-mono text-[9px] uppercase tracking-widest text-text-muted">
                            Retry themes ({snap.retry_themes.length})
                          </span>
                          <div className="mt-1 flex flex-wrap gap-1">
                            {snap.retry_themes.map(k => (
                              <span key={k} className="font-mono text-[9px] text-retry-amber-bright px-1.5 py-0.5 rounded bg-retry-amber/10 border border-retry-amber/30">
                                {k}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
