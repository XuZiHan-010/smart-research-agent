import { motion } from 'framer-motion'
import { ExternalLink, X } from 'lucide-react'
import clsx from 'clsx'
import { ThemeRunState, ThemeStatus } from '../types'

interface Props {
  theme:     ThemeRunState
  iteration: number
  onClose:   () => void
}

const STATUS_BADGE: Record<ThemeStatus, { cls: string; label: string }> = {
  pending:     { cls: 'text-text-muted bg-border/40 border-border',                            label: 'Pending' },
  researching: { cls: 'text-accent bg-accent/10 border-accent/30',                             label: 'Researching' },
  validating:  { cls: 'text-accent-bright bg-accent/10 border-accent-bright/30',               label: 'Validating' },
  retrying:    { cls: 'text-retry-amber-bright bg-retry-amber/10 border-retry-amber/30',       label: 'Retrying' },
  done:        { cls: 'text-active-green bg-active-green/10 border-active-green/30',           label: 'Resolved' },
  failed:      { cls: 'text-error-red bg-error-red/10 border-error-red/30',                    label: 'Failed' },
}

export function ThemeDetailDrawer({ theme, iteration, onClose }: Props) {
  const badge = STATUS_BADGE[theme.status]
  const score = theme.quality_score ?? 0

  return (
    <>
      {/* Backdrop */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
        className="fixed inset-0 bg-black/40 backdrop-blur-[2px] z-40"
      />

      {/* Drawer */}
      <motion.aside
        initial={{ x: '100%' }}
        animate={{ x: 0 }}
        exit={{ x: '100%' }}
        transition={{ ease: [0.16, 1, 0.3, 1], duration: 0.4 }}
        className="fixed top-0 right-0 bottom-0 w-[500px] max-w-[90vw] z-50 bg-surface border-l border-border
                   shadow-2xl overflow-y-auto"
      >
        {/* Header */}
        <div className="sticky top-0 bg-surface/95 backdrop-blur-md border-b border-border px-6 py-5 z-10">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2 mb-2">
                <span className={clsx(
                  'font-mono text-[9px] uppercase tracking-widest px-2 py-0.5 rounded border',
                  badge.cls,
                )}>
                  {badge.label}
                </span>
                <span className="font-mono text-[9px] uppercase tracking-widest text-text-muted">
                  Iter {String(iteration).padStart(2, '0')}
                </span>
                {theme.retry_count > 0 && (
                  <span className="font-mono text-[9px] text-retry-amber-bright">
                    ↻ retried {theme.retry_count}×
                  </span>
                )}
              </div>
              <h2 className="font-display text-2xl text-text-primary font-light italic">
                {theme.label}
              </h2>
              <p className="font-mono text-[10px] text-text-muted mt-1">
                {theme.theme_key}
              </p>
            </div>
            <button
              onClick={onClose}
              className="text-text-muted hover:text-text-primary p-1 -m-1"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        <div className="p-6 space-y-6">
          {/* Quality score */}
          <section>
            <SectionLabel>Quality Score</SectionLabel>
            {typeof theme.quality_score === 'number' ? (
              <div>
                <div className="flex items-baseline gap-2 mb-2">
                  <span className="font-mono text-5xl text-text-primary tabular-nums leading-none">
                    {score}
                  </span>
                  <span className="font-mono text-sm text-text-muted">/ 100</span>
                  {theme.confidence && (
                    <span className={clsx(
                      'ml-auto font-mono text-[10px] uppercase tracking-widest px-2 py-1 rounded border',
                      theme.confidence === 'high'   && 'text-active-green border-active-green/30 bg-active-green/10',
                      theme.confidence === 'medium' && 'text-accent border-accent/30 bg-accent/10',
                      theme.confidence === 'low'    && 'text-error-red border-error-red/30 bg-error-red/10',
                    )}>
                      {theme.confidence} confidence
                    </span>
                  )}
                </div>
                <div className="h-1.5 bg-border rounded-sm overflow-hidden relative">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${score}%` }}
                    transition={{ duration: 0.6, ease: 'easeOut' }}
                    className="h-full bg-quality-grad"
                  />
                </div>
              </div>
            ) : (
              <p className="text-text-muted text-sm font-mono italic">awaiting validation…</p>
            )}
          </section>

          {/* Metrics row */}
          <section className="grid grid-cols-3 gap-3">
            <Metric label="Docs" value={theme.docs_found} />
            <Metric label="Citations" value={theme.citations_count} />
            <Metric label="Retries" value={theme.retry_count} accent={theme.retry_count > 0} />
          </section>

          {/* Gaps */}
          {theme.gaps && theme.gaps.length > 0 && (
            <section>
              <SectionLabel>Flags & Gaps</SectionLabel>
              <div className="space-y-1.5">
                {theme.gaps.map((g, i) => (
                  <div key={i}
                    className="flex gap-2 text-xs text-text-secondary border border-retry-amber/20 bg-retry-amber/5 rounded px-3 py-2"
                  >
                    <span className="text-retry-amber-bright flex-shrink-0">▸</span>
                    <span>{g}</span>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Queries */}
          {theme.queries && theme.queries.length > 0 && (
            <section>
              <SectionLabel>Search Queries (Iter {iteration})</SectionLabel>
              <div className="space-y-1">
                {theme.queries.map((q, i) => (
                  <div key={i}
                    className="flex gap-2 font-mono text-[11px] text-text-muted leading-relaxed border-l border-border pl-3 py-0.5"
                  >
                    <span className="text-accent/60">›</span>
                    <span>{q}</span>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Sources */}
          {theme.sources && theme.sources.length > 0 && (
            <section>
              <SectionLabel>Sources ({theme.sources.length})</SectionLabel>
              <div className="space-y-2">
                {theme.sources.map(src => {
                  let hostname = ''
                  try { hostname = new URL(src.url).hostname.replace(/^www\./, '') } catch { hostname = src.url }
                  const scorePct = typeof src.score === 'number' ? Math.round(src.score * 100) : null
                  return (
                    <a
                      key={src.doc_id}
                      href={src.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="group block border border-border bg-elevated rounded p-3 hover:border-accent/40 transition-colors"
                    >
                      <div className="flex items-start justify-between gap-3 mb-1">
                        <div className="font-mono text-[10px] text-accent uppercase tracking-widest flex items-center gap-2">
                          <span>{hostname}</span>
                          {src.published && <span className="text-text-muted">· {src.published}</span>}
                        </div>
                        <ExternalLink size={11} className="text-text-muted group-hover:text-accent flex-shrink-0" />
                      </div>
                      <h4 className="text-sm text-text-primary leading-snug group-hover:text-accent transition-colors">
                        {src.title}
                      </h4>
                      {src.excerpt && (
                        <p className="text-xs text-text-secondary mt-1.5 leading-relaxed line-clamp-2">
                          {src.excerpt}
                        </p>
                      )}
                      {scorePct !== null && (
                        <div className="mt-2 flex items-center gap-2">
                          <div className="flex-1 h-0.5 bg-border rounded-sm overflow-hidden">
                            <div className="h-full bg-accent" style={{ width: `${scorePct}%` }} />
                          </div>
                          <span className="font-mono text-[9px] text-text-muted tabular-nums">
                            {scorePct}%
                          </span>
                        </div>
                      )}
                    </a>
                  )
                })}
              </div>
            </section>
          )}

          {/* Empty state */}
          {!theme.queries?.length && !theme.sources?.length && !theme.gaps?.length && (
            <div className="text-center py-12">
              <div className="font-display text-lg text-text-muted italic">no detail yet</div>
              <p className="text-xs text-text-muted mt-2 font-mono">
                detail emerges as the agent researches…
              </p>
            </div>
          )}
        </div>
      </motion.aside>
    </>
  )
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="font-mono text-[9px] uppercase tracking-[0.18em] text-text-muted mb-3">
      {children}
    </div>
  )
}

function Metric({ label, value, accent }: { label: string; value: number; accent?: boolean }) {
  return (
    <div className="border border-border bg-elevated rounded p-3">
      <div className="font-mono text-[9px] uppercase tracking-widest text-text-muted">{label}</div>
      <div className={clsx(
        'font-mono text-2xl tabular-nums mt-1',
        accent ? 'text-retry-amber-bright' : 'text-text-primary',
      )}>
        {value}
      </div>
    </div>
  )
}
