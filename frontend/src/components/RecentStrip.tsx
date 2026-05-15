import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { Clock, ArrowUpRight } from 'lucide-react'
import { HistoryJob } from '../types'

const API = import.meta.env.VITE_API_URL ?? ''

interface Props {
  onLoad: (jobId: string, report: string) => void
}

export function RecentStrip({ onLoad }: Props) {
  const [jobs, setJobs] = useState<HistoryJob[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const res = await fetch(`${API}/api/research/history?limit=3`)
        const data = await res.json()
        if (!cancelled) setJobs((data.jobs ?? []).slice(0, 3))
      } catch {
        if (!cancelled) setJobs([])
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [])

  const handleClick = async (job: HistoryJob) => {
    if (job.status !== 'completed') return
    try {
      const res = await fetch(`${API}/api/research/${job.id}/report`)
      const data = await res.json()
      if (data.report) onLoad(job.id, data.report)
    } catch {}
  }

  if (loading || jobs.length === 0) return null

  return (
    <div>
      <div className="flex items-center gap-3 mb-3 text-text-muted">
        <span className="flex-1 h-px bg-border" />
        <span className="font-mono text-[10px] uppercase tracking-[0.3em]">Recent</span>
        <span className="flex-1 h-px bg-border" />
      </div>

      <div className="grid grid-cols-3 gap-3">
        {jobs.map((job, i) => (
          <motion.button
            key={job.id}
            type="button"
            onClick={() => handleClick(job)}
            disabled={job.status !== 'completed'}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 + i * 0.06, duration: 0.35 }}
            whileHover={job.status === 'completed' ? { y: -2 } : {}}
            className="group text-left p-3 rounded border border-border bg-elevated/50
                       hover:border-accent/40 hover:bg-elevated transition-colors
                       disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <div className="flex items-center justify-between mb-2">
              <StatusDot status={job.status} />
              <ArrowUpRight
                size={11}
                className="text-text-muted group-hover:text-accent transition-colors flex-shrink-0"
              />
            </div>
            <div className="text-sm text-text-primary font-medium leading-snug line-clamp-2 mb-2 min-h-[2.4em]">
              {job.research_domain}
            </div>
            <div className="flex items-center gap-1.5 text-text-muted">
              <Clock size={9} />
              <span className="font-mono text-[10px]">{formatDate(job.created_at)}</span>
            </div>
          </motion.button>
        ))}
      </div>
    </div>
  )
}

function StatusDot({ status }: { status: HistoryJob['status'] }) {
  const cfg = {
    completed: { cls: 'text-active-green border-active-green/30 bg-active-green/10', label: 'Done' },
    running:   { cls: 'text-accent border-accent/30 bg-accent/10',                   label: 'Running' },
    failed:    { cls: 'text-error-red border-error-red/30 bg-error-red/10',          label: 'Failed' },
  }[status]
  return (
    <span className={`font-mono text-[9px] uppercase tracking-widest px-1.5 py-0.5 rounded border ${cfg.cls}`}>
      {cfg.label}
    </span>
  )
}

function formatDate(iso: string): string {
  try {
    const d = new Date(iso)
    const now = new Date()
    const diffMs = now.getTime() - d.getTime()
    const diffH = diffMs / (1000 * 60 * 60)
    if (diffH < 1) return `${Math.max(1, Math.floor(diffMs / 60000))}m ago`
    if (diffH < 24) return `${Math.floor(diffH)}h ago`
    if (diffH < 24 * 7) return `${Math.floor(diffH / 24)}d ago`
    return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
  } catch {
    return iso.slice(0, 10)
  }
}
