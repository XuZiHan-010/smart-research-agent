import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { RefreshCw, X } from 'lucide-react'
import { AgentTrace } from '../types'

const API = import.meta.env.VITE_API_URL ?? ''

interface Props {
  open: boolean
  jobId?: string | null
  onClose: () => void
}

export function TracesDrawer({ open, jobId, onClose }: Props) {
  const [traces, setTraces] = useState<AgentTrace[]>([])
  const [loading, setLoading] = useState(false)

  const fetchTraces = async () => {
    if (!jobId) return
    setLoading(true)
    try {
      const res = await fetch(`${API}/api/research/${jobId}/traces`)
      const data = await res.json()
      setTraces(data.traces ?? [])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { if (open) fetchTraces() }, [open, jobId])

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose} className="fixed inset-0 bg-black/40 z-30" />
          <motion.aside initial={{ x: '100%' }} animate={{ x: 0 }} exit={{ x: '100%' }} transition={{ type: 'spring', damping: 28, stiffness: 280 }} className="fixed right-0 top-0 bottom-0 w-[30rem] bg-surface border-l border-border z-40 flex flex-col shadow-2xl">
            <div className="flex items-center justify-between px-5 py-4 border-b border-border">
              <div>
                <span className="font-mono text-xs text-accent uppercase tracking-widest">Agent Decisions</span>
                <p className="text-[11px] text-text-muted font-mono mt-0.5">{traces.length} trace{traces.length !== 1 ? 's' : ''}</p>
              </div>
              <div className="flex items-center gap-2">
                <button onClick={fetchTraces} className="p-1.5 text-text-muted hover:text-text-primary rounded hover:bg-elevated">
                  <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
                </button>
                <button onClick={onClose} className="p-1.5 text-text-muted hover:text-text-primary"><X size={15} /></button>
              </div>
            </div>
            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              {traces.map((trace, idx) => (
                <div key={`${trace.created_at}-${idx}`} className="border border-border bg-elevated rounded p-3">
                  <div className="flex items-center justify-between gap-3 mb-2">
                    <span className="font-mono text-[10px] text-accent uppercase">{trace.node}</span>
                    <span className="font-mono text-[10px] text-text-muted">{trace.model}</span>
                  </div>
                  <p className="text-[11px] text-text-muted font-mono mb-2">{trace.prompt_name}</p>
                  <p className="text-xs text-text-secondary leading-relaxed">{trace.output_summary || trace.input_summary}</p>
                </div>
              ))}
              {!loading && traces.length === 0 && <p className="text-text-muted text-xs font-mono">No traces recorded yet.</p>}
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  )
}
