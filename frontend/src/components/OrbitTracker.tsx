import { useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { RotateCw } from 'lucide-react'
import clsx from 'clsx'
import {
  PipelineStage,
  ThemeRunState,
  ThemeStatus,
  ValidationSnapshot,
} from '../types'
import { ThemeDetailDrawer } from './ThemeDetailDrawer'
import { ValidationTimeline } from './ValidationTimeline'

interface Props {
  stages:         PipelineStage[]
  statusMessage:  string
  iteration:      number
  themeStates:    Record<string, ThemeRunState>
  validations:    ValidationSnapshot[]
  retryArc:       { id: number; themes: string[]; reason?: string } | null
  logLines:       string[]
  researchDomain?: string
}

// ── geometry ─────────────────────────────────────────────────────────────────
const VIEW = 340
const CENTER = VIEW / 2
const ORBIT_R = 118
const NODE_R_BASE = 11
const NODE_R_ACTIVE = 15

const angleFor = (idx: number, total: number): number =>
  (idx / total) * Math.PI * 2 - Math.PI / 2

const polar = (angle: number, radius: number) => ({
  x: CENTER + Math.cos(angle) * radius,
  y: CENTER + Math.sin(angle) * radius,
})

// ── visual mapping ───────────────────────────────────────────────────────────
const STATUS_FILL: Record<ThemeStatus, string> = {
  pending:     'fill-elevated stroke-border',
  researching: 'fill-accent/30 stroke-accent',
  validating:  'fill-accent/20 stroke-accent-bright',
  retrying:    'fill-retry-amber/25 stroke-retry-amber-bright',
  done:        'fill-active-green/80 stroke-active-green',
  failed:      'fill-error-red/40 stroke-error-red',
}

const STATUS_LABEL: Record<ThemeStatus, string> = {
  pending:     'Idle',
  researching: 'Researching',
  validating:  'Validating',
  retrying:    'Retrying',
  done:        'Done',
  failed:      'Failed',
}

const CONFIDENCE_TEXT: Record<NonNullable<ThemeRunState['confidence']>, string> = {
  high: '高', medium: '中', low: '低',
}

// ── component ────────────────────────────────────────────────────────────────
export function OrbitTracker({
  stages, statusMessage, iteration, themeStates, validations, retryArc, logLines, researchDomain,
}: Props) {
  const [selectedKey, setSelectedKey] = useState<string | null>(null)
  const themes = useMemo(() => Object.values(themeStates), [themeStates])
  const total = Math.max(themes.length, 1)

  const doneCount = stages.filter(s => s.status === 'done').length
  const pct = Math.round((doneCount / stages.length) * 100)
  const isRetrying = stages.some(s => s.status === 'retrying') || !!retryArc

  // active arc endpoints (between retried theme indices)
  const retryArcD = useMemo(() => {
    if (!retryArc || themes.length === 0) return null
    const indices = retryArc.themes
      .map(k => themes.findIndex(t => t.theme_key === k))
      .filter(i => i >= 0)
    if (indices.length < 1) return null
    const from = angleFor(indices[0], total)
    const to = angleFor(indices[indices.length - 1] ?? indices[0], total)
    const r = ORBIT_R + 28
    const start = polar(from, r)
    const end = polar(to, r)
    const sweep = indices.length > 1 ? 1 : 0
    const large = Math.abs(to - from) > Math.PI ? 1 : 0
    return `M ${start.x} ${start.y} A ${r} ${r} 0 ${large} ${sweep} ${end.x} ${end.y}`
  }, [retryArc, themes, total])

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex flex-col gap-6 h-full"
    >
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div className="flex items-end justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-baseline gap-3">
            <h2 className="font-display text-3xl font-light italic text-text-primary leading-none">
              {isRetrying ? 'Refining' : 'Researching'}
              <span className="text-accent not-italic">.</span>
            </h2>
            <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-text-muted">
              Iteration
            </span>
            <span className="font-mono text-xl text-accent tabular-nums leading-none">
              {String(iteration).padStart(2, '0')}
            </span>
          </div>
          {researchDomain && (
            <p className="mt-1.5 text-text-secondary text-xs font-body truncate max-w-md">
              {researchDomain}
            </p>
          )}
          <p className="mt-0.5 text-text-muted text-[11px] font-mono truncate max-w-md">
            {statusMessage || 'Initializing pipeline…'}
          </p>
        </div>

        <div className="text-right flex-shrink-0">
          <div className="font-mono text-3xl text-accent tabular-nums leading-none">{pct}<span className="text-base text-text-muted ml-0.5">%</span></div>
          <div className="font-mono text-[9px] uppercase tracking-widest text-text-muted mt-1">complete</div>
        </div>
      </div>

      {/* ── Progress shimmer line ──────────────────────────────────────── */}
      <div className="h-px bg-border relative overflow-hidden -mt-2">
        <motion.div
          className={clsx('absolute inset-y-0 left-0', isRetrying ? 'bg-retry-amber' : 'bg-accent')}
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.4 }}
        />
        {pct < 100 && (
          <div className="absolute inset-0 bg-gradient-to-r from-transparent via-accent/40 to-transparent
                          animate-shimmer bg-[length:200%_100%]" />
        )}
      </div>

      {/* ── Orbit visualization ────────────────────────────────────────── */}
      <div className="relative flex items-center justify-center">
        <div
          className={clsx(
            'relative rounded-full bg-orbit-halo',
            retryArc && 'animate-quake',
          )}
          style={{ width: VIEW, height: VIEW }}
        >
          <svg
            viewBox={`0 0 ${VIEW} ${VIEW}`}
            className={clsx('w-full h-full', isRetrying ? '' : 'animate-spin-slow')}
            style={{ animationPlayState: themes.some(t => t.status === 'researching') ? 'running' : 'paused' }}
          >
            {/* Orbit ring */}
            <circle
              cx={CENTER} cy={CENTER} r={ORBIT_R}
              fill="none"
              stroke="currentColor"
              className="text-border"
              strokeWidth={1}
              strokeDasharray="2 4"
            />
            {/* Inner orbit accent */}
            <circle
              cx={CENTER} cy={CENTER} r={ORBIT_R - 28}
              fill="none"
              stroke="currentColor"
              className="text-border/40"
              strokeWidth={1}
            />

            {/* Retry arc (animated) */}
            <AnimatePresence>
              {retryArc && retryArcD && (
                <motion.path
                  key={retryArc.id}
                  d={retryArcD}
                  stroke="#f59e0b"
                  strokeWidth={2}
                  fill="none"
                  strokeDasharray="240"
                  strokeLinecap="round"
                  initial={{ strokeDashoffset: 240, opacity: 0 }}
                  animate={{ strokeDashoffset: 0, opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }}
                />
              )}
            </AnimatePresence>

            {/* Theme nodes */}
            {themes.map((t, i) => {
              const angle = angleFor(i, total)
              const { x, y } = polar(angle, ORBIT_R)
              const active = t.status === 'researching' || t.status === 'validating'
              const r = active ? NODE_R_ACTIVE : NODE_R_BASE

              return (
                <g
                  key={t.theme_key}
                  onClick={() => setSelectedKey(t.theme_key)}
                  className="cursor-pointer"
                  style={{ transformBox: 'fill-box', transformOrigin: 'center' }}
                >
                  {/* Pulse halo for active */}
                  {active && (
                    <circle
                      cx={x} cy={y} r={r}
                      className="fill-accent/20 stroke-accent animate-orbit-pulse"
                      strokeWidth={1}
                    />
                  )}
                  {/* Retry halo */}
                  {t.status === 'retrying' && (
                    <circle
                      cx={x} cy={y} r={r + 4}
                      className="fill-none stroke-retry-amber-bright animate-pulse"
                      strokeWidth={1.5}
                      strokeDasharray="3 3"
                    />
                  )}
                  {/* Node */}
                  <motion.circle
                    cx={x} cy={y}
                    r={r}
                    className={clsx(STATUS_FILL[t.status], 'transition-all')}
                    strokeWidth={1.5}
                    animate={active ? { r: [r - 2, r + 2, r - 2] } : { r }}
                    transition={{ duration: 1.6, repeat: active ? Infinity : 0 }}
                  />
                  {/* Retry counter badge */}
                  {t.retry_count > 0 && (
                    <g>
                      <circle cx={x + r * 0.85} cy={y - r * 0.85} r={5}
                        className="fill-base stroke-retry-amber-bright" strokeWidth={1} />
                      <text x={x + r * 0.85} y={y - r * 0.85 + 1.6}
                        textAnchor="middle"
                        className="fill-retry-amber-bright font-mono"
                        fontSize={6}
                        style={{ fontFamily: 'JetBrains Mono, monospace' }}
                      >
                        {t.retry_count}
                      </text>
                    </g>
                  )}
                  {/* Quality dot */}
                  {typeof t.quality_score === 'number' && t.status === 'done' && (
                    <circle cx={x - r * 0.6} cy={y + r * 0.85} r={2.5}
                      className={clsx(
                        t.quality_score >= 80 ? 'fill-active-green' :
                        t.quality_score >= 60 ? 'fill-accent' :
                        'fill-error-red'
                      )}
                    />
                  )}
                </g>
              )
            })}

            {/* Theme labels (outside ring) */}
            {themes.map((t, i) => {
              const angle = angleFor(i, total)
              const labelR = ORBIT_R + 44
              const { x, y } = polar(angle, labelR)
              const anchor =
                Math.abs(Math.cos(angle)) < 0.2 ? 'middle' :
                Math.cos(angle) > 0 ? 'start' : 'end'
              return (
                <text
                  key={`label-${t.theme_key}`}
                  x={x} y={y}
                  textAnchor={anchor}
                  dominantBaseline="middle"
                  className={clsx(
                    'pointer-events-none transition-colors',
                    t.status === 'done' && 'fill-active-green',
                    t.status === 'researching' && 'fill-accent',
                    t.status === 'retrying' && 'fill-retry-amber-bright',
                    t.status === 'failed' && 'fill-error-red',
                    (t.status === 'pending' || t.status === 'validating') && 'fill-text-muted',
                  )}
                  fontSize={8.5}
                  style={{ fontFamily: 'JetBrains Mono, monospace', letterSpacing: '0.05em' }}
                >
                  {abbreviate(t.label)}
                </text>
              )
            })}
          </svg>

          {/* Center info */}
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <div className="text-center">
              <div className="font-mono text-[9px] uppercase tracking-widest text-text-muted">
                {themes.filter(t => t.status === 'done').length} / {themes.length}
              </div>
              <div className="font-display text-2xl text-text-primary italic mt-0.5">
                themes
              </div>
              {isRetrying && (
                <div className="mt-2 flex items-center justify-center gap-1 text-retry-amber-bright">
                  <RotateCw size={10} className="animate-spin" style={{ animationDuration: '2s' }} />
                  <span className="font-mono text-[9px] uppercase tracking-widest">retry</span>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* ── Theme list (compact rows) ──────────────────────────────────── */}
      <div className="space-y-1 border-t border-border pt-4">
        <div className="font-mono text-[9px] uppercase tracking-[0.18em] text-text-muted mb-2 flex justify-between">
          <span>Theme · Quality · Sources</span>
          <span>{themes.filter(t => t.status === 'done').length} resolved</span>
        </div>
        {themes.map(t => (
          <ThemeRow key={t.theme_key} t={t} onClick={() => setSelectedKey(t.theme_key)} />
        ))}
      </div>

      {/* ── Validation timeline ────────────────────────────────────────── */}
      {validations.length > 0 && (
        <ValidationTimeline snapshots={validations} currentIteration={iteration} />
      )}

      {/* ── Mini log terminal ──────────────────────────────────────────── */}
      <div className="border border-border rounded bg-elevated/60 backdrop-blur-sm px-3 py-2 font-mono text-[10px]
                      space-y-0.5 max-h-32 overflow-y-auto flex-shrink-0">
        {logLines.length === 0 && <span className="text-text-muted">› awaiting pipeline events…</span>}
        {logLines.slice(-30).map((line, i) => (
          <div key={i} className="flex gap-2 leading-relaxed">
            <span className="text-accent/60 flex-shrink-0">›</span>
            <span className="text-text-muted break-all">{line}</span>
          </div>
        ))}
        <span className="text-accent animate-blink">▌</span>
      </div>

      {/* ── Theme detail drawer ────────────────────────────────────────── */}
      <AnimatePresence>
        {selectedKey && themeStates[selectedKey] && (
          <ThemeDetailDrawer
            theme={themeStates[selectedKey]}
            iteration={iteration}
            onClose={() => setSelectedKey(null)}
          />
        )}
      </AnimatePresence>
    </motion.div>
  )
}

// ── Sub-component: compact theme row ─────────────────────────────────────────
function ThemeRow({ t, onClick }: { t: ThemeRunState; onClick: () => void }) {
  const score = t.quality_score ?? 0
  return (
    <button
      onClick={onClick}
      className="w-full group flex items-center gap-3 px-2 py-1.5 rounded text-left
                 hover:bg-elevated/60 transition-colors"
    >
      {/* Status indicator */}
      <span className={clsx(
        'w-1 h-6 rounded-sm flex-shrink-0 transition-all',
        t.status === 'done' && 'bg-active-green',
        t.status === 'researching' && 'bg-accent animate-pulse',
        t.status === 'validating' && 'bg-accent-bright',
        t.status === 'retrying' && 'bg-retry-amber-bright animate-pulse',
        t.status === 'failed' && 'bg-error-red',
        t.status === 'pending' && 'bg-border',
      )} />

      {/* Label */}
      <span className="text-xs text-text-secondary font-body truncate flex-1 min-w-0 group-hover:text-text-primary">
        {t.label}
        {t.retry_count > 0 && (
          <span className="ml-2 text-[9px] font-mono text-retry-amber-bright">
            ↻{t.retry_count}
          </span>
        )}
      </span>

      {/* Quality bar */}
      <div className="w-20 flex-shrink-0">
        {typeof t.quality_score === 'number' ? (
          <div className="h-1 bg-border rounded-sm overflow-hidden relative">
            <div
              className="h-full bg-quality-grad transition-all"
              style={{ width: `${score}%` }}
            />
          </div>
        ) : (
          <div className="h-1 bg-border/40 rounded-sm" />
        )}
      </div>

      {/* Confidence + docs */}
      <span className="font-mono text-[10px] text-text-muted w-12 text-right tabular-nums flex-shrink-0">
        {t.confidence && (
          <span className={clsx(
            'mr-1',
            t.confidence === 'high' && 'text-active-green',
            t.confidence === 'medium' && 'text-accent',
            t.confidence === 'low' && 'text-error-red',
          )}>
            {CONFIDENCE_TEXT[t.confidence]}
          </span>
        )}
        {t.docs_found}d
      </span>

      {/* Status label */}
      <span className={clsx(
        'font-mono text-[9px] uppercase tracking-widest w-20 text-right flex-shrink-0',
        t.status === 'done' && 'text-active-green',
        t.status === 'researching' && 'text-accent',
        t.status === 'retrying' && 'text-retry-amber-bright',
        t.status === 'failed' && 'text-error-red',
        (t.status === 'pending' || t.status === 'validating') && 'text-text-muted',
      )}>
        {STATUS_LABEL[t.status]}
      </span>
    </button>
  )
}

// ── helpers ──────────────────────────────────────────────────────────────────
function abbreviate(label: string): string {
  // For Chinese labels, take first 4 chars; for English, first 2 words
  if (/[一-龥]/.test(label)) return label.slice(0, 4)
  return label.split(' ').slice(0, 2).join(' ').slice(0, 14)
}
