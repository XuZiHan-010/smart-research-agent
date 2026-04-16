import { motion } from 'framer-motion'
import { PipelineStage, TodoState, CellStatus, DIMENSION_LABELS } from '../types'

interface Props {
  stages:        PipelineStage[]
  statusMessage: string
  todoState:     TodoState
  dimLabels:     Record<string, string>
  logLines:      string[]
}

// ── Cell status → colour mapping ──────────────────────────────────────────────

const CELL_BG: Record<CellStatus, string> = {
  pending: 'bg-border animate-pulse',
  success: 'bg-active-green/70',
  partial: 'bg-yellow-500/60',
  empty:   'bg-elevated border border-border',
  error:   'bg-error-red/60',
}

const CELL_TITLE: Record<CellStatus, string> = {
  pending: 'Pending',
  success: 'Success',
  partial: 'Partial',
  empty:   'Empty',
  error:   'Error',
}

// ── Stage node colour ─────────────────────────────────────────────────────────

const STAGE_COLOR: Record<string, string> = {
  idle:   'text-text-muted border-border',
  active: 'text-accent border-accent shadow-accent/20 shadow-lg',
  done:   'text-active-green border-active-green',
  error:  'text-error-red border-error-red',
}

// ── Components ────────────────────────────────────────────────────────────────

export function ProgressTracker({ stages, statusMessage, todoState, dimLabels, logLines }: Props) {
  const companies  = Object.keys(todoState)
  const dims       = Object.keys(dimLabels).length > 0 ? Object.keys(dimLabels) : Object.keys(DIMENSION_LABELS)
  const doneCount  = stages.filter(s => s.status === 'done').length
  const pct        = Math.round((doneCount / stages.length) * 100)
  const hasTodo    = companies.length > 0

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex flex-col gap-5 h-full"
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-display text-2xl font-light text-text-primary tracking-wide">
            Researching<span className="text-accent">.</span>
          </h2>
          <p className="text-text-secondary text-xs mt-0.5 font-mono truncate max-w-xs">
            {statusMessage || 'Initializing pipeline…'}
          </p>
        </div>
        <div className="text-right">
          <div className="font-mono text-2xl text-accent">{pct}%</div>
          <div className="font-mono text-[10px] text-text-muted">complete</div>
        </div>
      </div>

      {/* Progress bar */}
      <div className="h-px bg-border relative overflow-hidden">
        <motion.div
          className="absolute inset-y-0 left-0 bg-accent"
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.4 }}
        />
        {pct < 100 && (
          <div className="absolute inset-0 bg-gradient-to-r from-transparent via-accent/40 to-transparent
                          animate-shimmer bg-[length:200%_100%]" />
        )}
      </div>

      {/* Pipeline nodes */}
      <div className="grid grid-cols-10 gap-0.5">
        {stages.map((stage, i) => (
          <div key={stage.id} className="flex flex-col items-center gap-1">
            <div className="flex items-center w-full relative">
              {i > 0 && (
                <div className={`absolute right-1/2 top-3.5 h-px w-full
                  ${stage.status !== 'idle' ? 'bg-accent/30' : 'bg-border'}`}
                />
              )}
              <div className={`relative z-10 w-7 h-7 rounded-full border flex items-center
                              justify-center mx-auto transition-all duration-300
                              ${STAGE_COLOR[stage.status]}`}
              >
                {stage.status === 'active' && (
                  <span className="absolute inset-0 rounded-full border border-accent animate-ping opacity-30" />
                )}
                {stage.status === 'done'  && <CheckIcon />}
                {stage.status === 'active' && <span className="w-1.5 h-1.5 rounded-full bg-accent" />}
                {stage.status === 'idle'  && <span className="font-mono text-[8px] text-text-muted">{i+1}</span>}
                {stage.status === 'error' && <span className="font-mono text-[9px]">✗</span>}
              </div>
            </div>
            <span className={`font-mono text-[7px] uppercase tracking-wide text-center leading-tight
              ${stage.status === 'active' ? 'text-accent' :
                stage.status === 'done'   ? 'text-active-green' : 'text-text-muted'}`}
            >
              {stage.label}
            </span>
          </div>
        ))}
      </div>

      {/* N×M Research Matrix */}
      {hasTodo && (
        <div className="border border-border rounded bg-elevated p-3">
          <p className="font-mono text-[10px] uppercase tracking-widest text-text-muted mb-3">
            Research Matrix — {companies.length} co. × {dims.length} dim.
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-[9px] font-mono border-collapse">
              <thead>
                <tr>
                  <th className="text-left pb-2 pr-3 text-text-muted font-normal w-24">Company</th>
                  {dims.map(d => (
                    <th key={d} className="pb-2 px-1 text-text-muted font-normal text-center">
                      {(dimLabels[d] || DIMENSION_LABELS[d] || d).split(' ')[0]}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {companies.map(company => (
                  <tr key={company}>
                    <td className="pr-3 py-1 text-text-secondary truncate max-w-[96px]">
                      {company}
                    </td>
                    {dims.map(dim => {
                      const cell = todoState[company]?.[dim]
                      const status: CellStatus = (cell?.status as CellStatus) || 'pending'
                      return (
                        <td key={dim} className="px-1 py-1 text-center">
                          <span
                            title={`${company} / ${dim}: ${CELL_TITLE[status]} (${cell?.docs_found ?? 0} docs)`}
                            className={`inline-block w-4 h-4 rounded-sm ${CELL_BG[status]}`}
                          />
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Legend */}
          <div className="flex items-center gap-3 mt-3 flex-wrap">
            {(Object.entries(CELL_BG) as [CellStatus, string][]).map(([status, cls]) => (
              <span key={status} className="flex items-center gap-1">
                <span className={`inline-block w-2.5 h-2.5 rounded-sm ${cls.replace('animate-pulse','')}`} />
                <span className="text-[9px] text-text-muted font-mono capitalize">{status}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Log terminal */}
      <div className="border border-border rounded bg-elevated p-3 font-mono text-[10px]
                      space-y-1 flex-1 overflow-y-auto min-h-[80px] max-h-48">
        {logLines.length === 0 && (
          <span className="text-text-muted">Waiting for pipeline events…</span>
        )}
        {logLines.map((line, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, x: -4 }}
            animate={{ opacity: 1, x: 0 }}
            className="flex gap-2 leading-relaxed"
          >
            <span className="text-accent flex-shrink-0">›</span>
            <span className="text-text-muted break-all">{line}</span>
          </motion.div>
        ))}
        {/* Blinking cursor on last line */}
        <span className="text-accent animate-blink">▌</span>
      </div>
    </motion.div>
  )
}

const CheckIcon = () => (
  <svg viewBox="0 0 10 8" className="w-2.5 h-2.5 stroke-current fill-none" strokeWidth="1.5">
    <path d="M1 4l2.5 2.5L9 1" />
  </svg>
)
