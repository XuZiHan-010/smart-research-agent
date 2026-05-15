import { useState } from 'react'
import { motion } from 'framer-motion'
import { ArrowRight } from 'lucide-react'
import { ResearchConfig } from '../types'
import { RecentStrip } from './RecentStrip'

interface Props {
  onStart: (config: ResearchConfig) => void
  onLoadHistory: (jobId: string, report: string) => void
}

const EXAMPLES = ['低空经济', '洞巾', '储能电站', '跨境SaaS']

export function EmptyState({ onStart, onLoadHistory }: Props) {
  const [value, setValue] = useState('')
  const [pulseKey, setPulseKey] = useState(0)

  const submit = () => {
    const v = value.trim()
    if (v.length === 0) return
    onStart({ researchDomain: v, depth: 'standard' })
  }

  const pickExample = (text: string) => {
    setValue(text)
    setPulseKey(k => k + 1)
  }

  const fade = (delay: number) => ({
    initial: { opacity: 0, y: 12 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.5, delay, ease: [0.16, 1, 0.3, 1] as const },
  })

  return (
    <div className="relative h-full w-full overflow-hidden">
      {/* Corner ornaments */}
      <CornerMark className="top-4 left-4" rotate={0} />
      <CornerMark className="top-4 right-4" rotate={90} />
      <CornerMark className="bottom-4 left-4" rotate={-90} />
      <CornerMark className="bottom-4 right-4" rotate={180} />

      <div className="relative h-full flex flex-col items-center justify-center px-8">
        <div className="w-full max-w-3xl">
          {/* Header */}
          <motion.div {...fade(0)} className="text-center mb-10">
            <div className="font-mono text-[10px] tracking-[0.32em] uppercase text-accent/80 mb-5">
              <span className="inline-block px-3 py-1 border border-accent/30 rounded-sm">
                Market Study Agent · v4.0
              </span>
            </div>
            <h1 className="font-display text-5xl md:text-6xl font-light italic text-text-primary leading-[1.05] mb-4">
              What market do you want to <span className="text-accent">understand</span>?
            </h1>
            <p className="font-body text-sm text-text-secondary max-w-xl mx-auto leading-relaxed">
              一句话描述你要研究的市场领域 — 我们会确认范围、并行调研多个主题、生成带引用的中文调研报告。
            </p>
          </motion.div>

          {/* Hero input */}
          <motion.div {...fade(0.08)} className="relative mb-6">
            {/* Radial glow behind input */}
            <div
              className="absolute inset-0 -m-12 bg-orbit-halo opacity-60 pointer-events-none animate-pulse-slow"
              aria-hidden
            />
            <div className="relative">
              <input
                key={pulseKey}
                value={value}
                onChange={e => setValue(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') submit() }}
                placeholder="e.g. 中国新能源汽车动力电池市场"
                className="w-full h-14 pl-5 pr-16 bg-elevated/80 backdrop-blur-sm border border-border-bright/60 rounded
                           text-text-primary text-base font-body placeholder:text-text-muted
                           outline-none transition-all
                           focus:border-accent focus:ring-2 focus:ring-accent/20
                           animate-token-pop"
              />
              <motion.button
                type="button"
                onClick={submit}
                disabled={value.trim().length === 0}
                whileTap={{ opacity: 0.8 }}
                whileHover={{ backgroundColor: 'rgb(240, 180, 69)' }}
                className="absolute right-2 inset-y-0 my-auto w-10 h-10 rounded
                           bg-accent flex items-center justify-center
                           disabled:opacity-30 disabled:cursor-not-allowed
                           shadow-lg shadow-accent/20 transition-colors"
                aria-label="Begin research"
              >
                <ArrowRight size={16} strokeWidth={2.4} />
              </motion.button>
            </div>
          </motion.div>

          {/* Example chips */}
          <motion.div {...fade(0.14)} className="flex items-center flex-wrap gap-2 justify-center mb-12">
            <span className="font-mono text-[10px] uppercase tracking-widest text-text-muted mr-1">
              Try ──
            </span>
            {EXAMPLES.map(ex => (
              <motion.button
                key={ex}
                type="button"
                onClick={() => pickExample(ex)}
                whileHover={{ y: -2 }}
                whileTap={{ scale: 0.96 }}
                className="px-3 py-1.5 font-mono text-xs rounded-sm
                           border border-border bg-elevated/40 text-text-secondary
                           hover:border-accent/60 hover:text-accent hover:bg-accent/5
                           transition-colors"
              >
                {ex}
              </motion.button>
            ))}
          </motion.div>

          {/* Recent jobs */}
          <motion.div {...fade(0.2)}>
            <RecentStrip onLoad={onLoadHistory} />
          </motion.div>
        </div>

        {/* Footer mark */}
        <motion.div
          {...fade(0.28)}
          className="absolute bottom-6 left-1/2 -translate-x-1/2 font-mono text-[10px] tracking-[0.32em] text-text-muted/50 uppercase"
        >
          ◆  System Ready  ◆
        </motion.div>
      </div>
    </div>
  )
}

function CornerMark({ className, rotate }: { className: string; rotate: number }) {
  return (
    <svg
      className={`absolute w-6 h-6 text-accent/25 pointer-events-none ${className}`}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.2"
      style={{ transform: `rotate(${rotate}deg)` }}
      aria-hidden
    >
      <path d="M2 8 V2 H8" />
      <line x1="2" y1="2" x2="10" y2="10" strokeOpacity="0.5" />
    </svg>
  )
}
