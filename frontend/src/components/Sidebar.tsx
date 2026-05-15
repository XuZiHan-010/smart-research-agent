import { motion } from 'framer-motion'
import { ArrowRight, RotateCcw } from 'lucide-react'
import { useState } from 'react'
import { ResearchConfig } from '../types'

interface Props {
  onStart: (config: ResearchConfig) => void
  onReset: () => void
  isRunning: boolean
}

export function Sidebar({ onStart, onReset, isRunning }: Props) {
  const [researchDomain, setResearchDomain] = useState('')

  const canSubmit = researchDomain.trim().length > 0

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!canSubmit) return
    onStart({ researchDomain: researchDomain.trim(), depth: 'standard' })
  }

  return (
    <aside className="w-72 flex-shrink-0 border-r border-border border-l-2 border-l-accent/20 bg-surface flex flex-col overflow-y-auto">
      <div className="px-5 py-4 border-b border-border">
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs text-accent tracking-wider">◆</span>
          <span className="font-mono text-xs text-accent tracking-widest uppercase">
            Market Study
          </span>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="flex-1 flex flex-col">
        <div className="p-5 space-y-6 flex-1">
          <section>
            <Label>↳ Research Domain</Label>
            <input
              value={researchDomain}
              onChange={e => setResearchDomain(e.target.value)}
              placeholder="中国新能源汽车动力电池市场"
              disabled={isRunning}
              className={inputCls}
            />
          </section>

          <div className="text-[10px] font-mono text-text-muted/60 uppercase tracking-widest space-y-1">
            <div>Validate → Research → Report</div>
          </div>
        </div>

        <div className="p-5 border-t border-border">
          {isRunning ? (
            <button
              type="button"
              onClick={onReset}
              className="w-full flex items-center justify-center gap-2 py-3 rounded border border-border text-text-secondary text-sm hover:border-border-bright hover:text-text-primary transition-colors"
            >
              <RotateCcw size={14} />
              Reset
            </button>
          ) : (
            <motion.button
              type="submit"
              disabled={!canSubmit}
              whileTap={{ scale: 0.97 }}
              className="w-full flex items-center justify-center gap-2 py-3.5 rounded bg-accent text-base font-medium text-sm hover:bg-accent-bright disabled:opacity-30 disabled:cursor-not-allowed transition-colors shadow-lg shadow-accent/10"
            >
              <span>Begin Research</span>
              <ArrowRight size={14} />
            </motion.button>
          )}
        </div>
      </form>
    </aside>
  )
}

const inputCls = `
  w-full bg-elevated border border-border rounded px-3 py-2 text-sm
  text-text-primary placeholder:text-text-muted font-body outline-none
  focus:border-accent focus:ring-1 focus:ring-accent/20
  disabled:opacity-40 transition-colors
`.replace(/\n\s+/g, ' ').trim()

function Label({ children }: { children: React.ReactNode }) {
  return <div className="font-mono text-[10px] uppercase tracking-widest text-text-muted mb-2">{children}</div>
}
