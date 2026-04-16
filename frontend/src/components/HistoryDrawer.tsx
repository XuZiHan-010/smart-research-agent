import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X, ExternalLink, RefreshCw } from 'lucide-react'
import { HistoryJob } from '../types'

const API = import.meta.env.VITE_API_URL ?? ''

interface Props {
  open:    boolean
  onClose: () => void
  onLoad:  (jobId: string, report: string) => void
}

export function HistoryDrawer({ open, onClose, onLoad }: Props) {
  const [jobs,    setJobs]    = useState<HistoryJob[]>([])
  const [loading, setLoading] = useState(false)

  const fetchHistory = async () => {
    setLoading(true)
    try {
      const res  = await fetch(`${API}/api/research/history?limit=50`)
      const data = await res.json()
      setJobs(data.jobs ?? [])
    } catch {
      setJobs([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { if (open) fetchHistory() }, [open])

  const handleLoad = async (job: HistoryJob) => {
    try {
      const res  = await fetch(`${API}/api/research/${job.id}/report`)
      const data = await res.json()
      if (data.report) {
        onLoad(job.id, data.report)
        onClose()
      }
    } catch {}
  }

  const handleDelete = async (jobId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    await fetch(`${API}/api/research/${jobId}`, { method: 'DELETE' })
    setJobs(prev => prev.filter(j => j.id !== jobId))
  }

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 bg-black/40 z-30"
          />

          {/* Drawer */}
          <motion.aside
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', damping: 28, stiffness: 280 }}
            className="fixed right-0 top-0 bottom-0 w-96 bg-surface border-l border-border z-40
                       flex flex-col shadow-2xl"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-4 border-b border-border flex-shrink-0">
              <div>
                <span className="font-mono text-xs text-accent uppercase tracking-widest">
                  Job History
                </span>
                <p className="text-[11px] text-text-muted font-mono mt-0.5">
                  {jobs.length} record{jobs.length !== 1 ? 's' : ''}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={fetchHistory}
                  className="p-1.5 text-text-muted hover:text-text-primary transition-colors
                             rounded hover:bg-elevated"
                >
                  <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
                </button>
                <button
                  onClick={onClose}
                  className="p-1.5 text-text-muted hover:text-text-primary transition-colors"
                >
                  <X size={15} />
                </button>
              </div>
            </div>

            {/* Job list */}
            <div className="flex-1 overflow-y-auto">
              {loading && (
                <div className="flex items-center justify-center h-32 text-text-muted font-mono text-xs">
                  Loading…
                </div>
              )}

              {!loading && jobs.length === 0 && (
                <div className="flex items-center justify-center h-32 text-text-muted font-mono text-xs">
                  No jobs found
                </div>
              )}

              {!loading && jobs.map(job => (
                <div
                  key={job.id}
                  onClick={() => job.status === 'completed' && handleLoad(job)}
                  className={`relative group border-b border-border px-5 py-4 transition-colors
                    ${job.status === 'completed'
                      ? 'hover:bg-elevated cursor-pointer'
                      : 'opacity-60 cursor-default'
                    }`}
                >
                  {/* Company + status */}
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-text-primary font-medium truncate">
                        {job.target_company}
                      </p>
                      <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
                        {job.competitors?.slice(0, 3).map(c => (
                          <span key={c} className="font-mono text-[10px] text-text-muted">
                            vs {c}
                          </span>
                        ))}
                        {(job.competitors?.length ?? 0) > 3 && (
                          <span className="font-mono text-[10px] text-text-muted">
                            +{job.competitors.length - 3} more
                          </span>
                        )}
                      </div>
                    </div>
                    <StatusBadge status={job.status} />
                  </div>

                  {/* Meta */}
                  <div className="flex items-center gap-2 text-[10px] font-mono text-text-muted">
                    <span className="capitalize">{job.report_type?.replace(/_/g, ' ')}</span>
                    <span>·</span>
                    <span className="capitalize">{job.depth?.replace('_', ' ')}</span>
                    <span>·</span>
                    <span>{new Date(job.created_at).toLocaleDateString()}</span>
                  </div>

                  {/* Load hint */}
                  {job.status === 'completed' && (
                    <div className="mt-2 flex items-center gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
                      <ExternalLink size={10} className="text-accent" />
                      <span className="font-mono text-[10px] text-accent">Load report</span>
                    </div>
                  )}

                  {/* Delete on hover */}
                  <button
                    type="button"
                    onClick={e => handleDelete(job.id, e)}
                    className="absolute right-4 top-4 opacity-0 group-hover:opacity-100
                               transition-opacity text-text-muted hover:text-error-red p-1 rounded"
                  >
                    <X size={12} />
                  </button>
                </div>
              ))}
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  )
}

function StatusBadge({ status }: { status: string }) {
  const cfg: Record<string, { label: string; cls: string }> = {
    completed: { label: 'Done',    cls: 'text-active-green border-active-green/40 bg-active-green/10' },
    running:   { label: 'Running', cls: 'text-accent border-accent/40 bg-accent/10' },
    failed:    { label: 'Failed',  cls: 'text-error-red border-error-red/40 bg-error-red/10' },
  }
  const { label, cls } = cfg[status] ?? { label: status, cls: 'text-text-muted border-border bg-transparent' }
  return (
    <span className={`px-2 py-0.5 text-[10px] font-mono border rounded flex-shrink-0 ${cls}`}>
      {label}
    </span>
  )
}
