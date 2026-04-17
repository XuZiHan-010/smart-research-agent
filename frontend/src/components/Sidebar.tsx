import { useState, useRef, KeyboardEvent } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Play, RotateCcw, Search, X, Plus, AlertTriangle } from 'lucide-react'
import {
  ResearchConfig, ReportType, ResearchDepth, OutputFormat, ReportLanguage,
  REPORT_TYPE_OPTIONS, DEPTH_CONFIG,
} from '../types'

interface Props {
  onStart:    (config: ResearchConfig) => void
  onDiscover: (config: ResearchConfig) => void
  onReset:    () => void
  isRunning:  boolean
}

export function Sidebar({ onStart, onDiscover, onReset, isRunning }: Props) {
  const [targetCompany,    setTarget]     = useState('')
  const [targetWebsite,    setWebsite]    = useState('')
  const [reportType,       setReportType] = useState<ReportType>('full_analysis')
  const [depth,            setDepth]      = useState<ResearchDepth>('standard')
  const [outputFormat,     setFormat]     = useState<OutputFormat>('markdown')
  const [language,         setLanguage]   = useState<ReportLanguage>('en')
  const [template,         setTemplate]   = useState('')
  const [showTemplate,     setShowTpl]    = useState(false)
  const [competitorNames,  setCompetitors]= useState<string[]>([])
  const [tagInput,         setTagInput]   = useState('')
  const [showNoCompWarn,   setShowWarn]   = useState(false)
  const tagRef = useRef<HTMLInputElement>(null)

  const cfg = (): ResearchConfig => ({
    target_company: targetCompany.trim(),
    target_website: targetWebsite.trim(),
    report_type:    reportType,
    depth,
    output_format:  outputFormat,
    language,
    template:       template.trim(),
    competitorNames,
  })

  const canSubmit = targetCompany.trim().length > 0

  // ── Tag input logic ────────────────────────────────────────────────────────

  const addTag = (name: string) => {
    const trimmed = name.trim()
    if (!trimmed || competitorNames.includes(trimmed)) return
    if (competitorNames.length >= 5) return
    setCompetitors(prev => [...prev, trimmed])
    setTagInput('')
  }

  const removeTag = (name: string) =>
    setCompetitors(prev => prev.filter(c => c !== name))

  const handleTagKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault()
      addTag(tagInput)
    }
    if (e.key === 'Backspace' && !tagInput && competitorNames.length > 0) {
      setCompetitors(prev => prev.slice(0, -1))
    }
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!canSubmit) return

    if (competitorNames.length === 0) {
      setShowWarn(true)
      return
    }

    onStart(cfg())
  }

  return (
    <aside className="w-72 flex-shrink-0 border-r border-border bg-surface flex flex-col overflow-y-auto">
      {/* Header */}
      <div className="px-5 py-4 border-b border-border">
        <div className="flex items-center gap-2">
          <div className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
          <span className="font-mono text-xs text-accent tracking-widest uppercase">
            Competitor Research
          </span>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="flex-1 flex flex-col">
        <div className="p-5 space-y-5 flex-1">

          {/* Target company */}
          <section>
            <Label>Target Company</Label>
            <input
              value={targetCompany}
              onChange={e => setTarget(e.target.value)}
              placeholder="e.g. Notion"
              disabled={isRunning}
              className={inputCls}
            />
          </section>

          {/* Website */}
          <section>
            <Label optional>Official Website</Label>
            <input
              value={targetWebsite}
              onChange={e => setWebsite(e.target.value)}
              placeholder="https://..."
              disabled={isRunning}
              className={inputCls}
            />
            <Hint>Crawls homepage for grounding context</Hint>
          </section>

          {/* Report type */}
          <section>
            <Label>Report Type</Label>
            <select
              value={reportType}
              onChange={e => setReportType(e.target.value as ReportType)}
              disabled={isRunning}
              className={`${inputCls} cursor-pointer`}
            >
              {REPORT_TYPE_OPTIONS.map(o => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
            <Hint>{REPORT_TYPE_OPTIONS.find(o => o.value === reportType)?.description}</Hint>
          </section>

          {/* Research Depth */}
          <section>
            <Label tooltip={
              <div className="space-y-2.5">
                {(Object.entries(DEPTH_CONFIG) as [ResearchDepth, typeof DEPTH_CONFIG.snapshot][]).map(([k, v]) => (
                  <div key={k}>
                    <span className="text-accent font-medium text-[10px] uppercase tracking-wider">
                      {v.label}
                    </span>
                    <span className="text-text-muted text-[10px]"> · {v.estimate}</span>
                    <p className="text-text-secondary text-[10px] leading-relaxed mt-0.5">
                      {v.description}
                    </p>
                  </div>
                ))}
              </div>
            }>
              Research Depth
            </Label>
            <div className="grid grid-cols-3 gap-px bg-border border border-border rounded overflow-hidden">
              {(Object.entries(DEPTH_CONFIG) as [ResearchDepth, typeof DEPTH_CONFIG.snapshot][]).map(([k, v]) => (
                <button
                  key={k}
                  type="button"
                  onClick={() => setDepth(k)}
                  disabled={isRunning}
                  className={`flex flex-col items-center py-2.5 text-xs transition-colors disabled:opacity-40
                    ${depth === k ? 'bg-accent/10 text-accent' : 'bg-elevated text-text-secondary hover:bg-surface'}`}
                >
                  <span className="font-medium mb-0.5">{v.label}</span>
                  <span className="font-mono text-text-muted text-[10px]">{v.estimate}</span>
                </button>
              ))}
            </div>
          </section>

          {/* Output Format */}
          <section>
            <Label>Output Format</Label>
            <div className="grid grid-cols-3 gap-px bg-border border border-border rounded overflow-hidden">
              {(['markdown', 'pdf', 'json'] as OutputFormat[]).map(fmt => (
                <button
                  key={fmt}
                  type="button"
                  onClick={() => setFormat(fmt)}
                  disabled={isRunning}
                  className={`py-2 text-xs font-mono uppercase tracking-wider transition-colors disabled:opacity-40
                    ${outputFormat === fmt ? 'bg-accent/10 text-accent' : 'bg-elevated text-text-secondary hover:bg-surface'}`}
                >
                  {fmt === 'markdown' ? 'MD' : fmt.toUpperCase()}
                </button>
              ))}
            </div>
          </section>

          {/* Report Language */}
          <section>
            <Label>Report Language</Label>
            <div className="grid grid-cols-2 gap-px bg-border border border-border rounded overflow-hidden">
              {([['en', 'English'], ['zh', '中文']] as [ReportLanguage, string][]).map(([lang, label]) => (
                <button
                  key={lang}
                  type="button"
                  onClick={() => setLanguage(lang)}
                  disabled={isRunning}
                  className={`py-2 text-xs font-mono transition-colors disabled:opacity-40
                    ${language === lang ? 'bg-accent/10 text-accent' : 'bg-elevated text-text-secondary hover:bg-surface'}`}
                >
                  {label}
                </button>
              ))}
            </div>
          </section>

          {/* Custom template */}
          <section>
            <div className="flex items-center justify-between mb-2">
              <Label inline>Report Template</Label>
              <button
                type="button"
                onClick={() => setShowTpl(v => !v)}
                className="font-mono text-[10px] text-accent hover:text-accent transition-colors flex items-center gap-1"
              >
                {showTemplate ? <RotateCcw size={9} /> : <Plus size={9} />}
                {showTemplate ? 'Use default' : 'Custom'}
              </button>
            </div>
            {!showTemplate && (
              <Hint>System template for selected report type</Hint>
            )}
            <AnimatePresence>
              {showTemplate && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  className="overflow-hidden"
                >
                  <textarea
                    value={template}
                    onChange={e => setTemplate(e.target.value)}
                    disabled={isRunning}
                    placeholder={`# {company} Report\n## Executive Summary\n## Market Position\n…`}
                    rows={7}
                    className="w-full bg-elevated border border-border rounded px-3 py-2
                               text-xs text-text-primary placeholder:text-text-muted
                               font-mono outline-none focus:border-accent
                               focus:ring-1 focus:ring-accent/20 disabled:opacity-40
                               resize-none leading-relaxed transition-colors"
                  />
                </motion.div>
              )}
            </AnimatePresence>
          </section>

          {/* Competitors tag input */}
          <section>
            <div className="flex items-center justify-between mb-2">
              <Label inline>Competitors</Label>
              <span className="font-mono text-[10px] text-text-muted">
                {competitorNames.length}/5 · press Enter to add
              </span>
            </div>

            {/* Tags + input */}
            <div
              onClick={() => tagRef.current?.focus()}
              className="min-h-[38px] flex flex-wrap gap-1.5 p-2 bg-elevated border border-border
                         rounded cursor-text focus-within:border-accent
                         focus-within:ring-1 focus-within:ring-accent/20 transition-colors"
            >
              {competitorNames.map(name => (
                <span
                  key={name}
                  className="inline-flex items-center gap-1 px-2 py-0.5 bg-accent/10 border
                             border-accent/30 rounded text-xs text-accent font-mono"
                >
                  {name}
                  <button
                    type="button"
                    onClick={() => removeTag(name)}
                    className="text-accent/60 hover:text-accent transition-colors"
                  >
                    <X size={10} />
                  </button>
                </span>
              ))}
              {competitorNames.length < 5 && (
                <input
                  ref={tagRef}
                  value={tagInput}
                  onChange={e => setTagInput(e.target.value)}
                  onKeyDown={handleTagKey}
                  onBlur={() => tagInput && addTag(tagInput)}
                  placeholder={competitorNames.length === 0 ? 'Type a name…' : ''}
                  disabled={isRunning}
                  className="flex-1 min-w-[80px] bg-transparent outline-none text-sm
                             text-text-primary placeholder:text-text-muted font-body"
                />
              )}
            </div>

            {/* Auto-discover button */}
            {!isRunning && (
              <button
                type="button"
                onClick={() => canSubmit && onDiscover(cfg())}
                disabled={!canSubmit}
                className="mt-2 w-full flex items-center justify-center gap-2 py-1.5
                           border border-border rounded text-xs font-mono text-text-secondary
                           hover:border-accent/50 hover:text-accent disabled:opacity-30
                           disabled:cursor-not-allowed transition-colors"
              >
                <Search size={11} />
                Auto-Discover Competitors
              </button>
            )}
            <Hint>Leave empty for full auto-discovery</Hint>
          </section>
        </div>

        {/* CTA */}
        <div className="p-5 border-t border-border space-y-2">
          {isRunning ? (
            <button
              type="button"
              onClick={onReset}
              className="w-full flex items-center justify-center gap-2 py-3 rounded
                         border border-border text-text-secondary text-sm
                         hover:border-border-bright hover:text-text-primary transition-colors"
            >
              <RotateCcw size={14} />
              Cancel
            </button>
          ) : (
            <motion.button
              type="submit"
              disabled={!canSubmit}
              whileTap={{ scale: 0.97 }}
              className="w-full flex items-center justify-center gap-2 py-3 rounded
                         bg-accent text-base font-medium text-sm
                         hover:bg-accent-bright disabled:opacity-30
                         disabled:cursor-not-allowed transition-colors
                         shadow-lg shadow-accent/10"
            >
              <Play size={14} />
              Start Research
            </motion.button>
          )}
        </div>
      </form>

      {/* No-competitors warning modal */}
      <AnimatePresence>
        {showNoCompWarn && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
            onClick={() => setShowWarn(false)}
          >
            <motion.div
              initial={{ scale: 0.95, y: 12 }}
              animate={{ scale: 1, y: 0 }}
              exit={{ scale: 0.95, y: 12 }}
              onClick={e => e.stopPropagation()}
              className="bg-surface border border-border rounded-lg w-full max-w-sm shadow-2xl"
            >
              {/* Header */}
              <div className="flex items-center gap-3 px-5 pt-5 pb-3">
                <div className="w-8 h-8 rounded-full bg-accent/10 border border-accent/30
                                flex items-center justify-center flex-shrink-0">
                  <AlertTriangle size={14} className="text-accent" />
                </div>
                <div>
                  <h3 className="text-sm font-medium text-text-primary">No competitors added</h3>
                  <p className="text-[11px] text-text-muted mt-0.5">
                    A competitive analysis needs competitors to compare against.
                  </p>
                </div>
              </div>

              {/* Body */}
              <div className="px-5 py-3 space-y-2.5">
                <div className="flex items-start gap-2.5 text-[12px] text-text-secondary">
                  <Search size={12} className="text-accent mt-0.5 flex-shrink-0" />
                  <span>
                    Use <span className="text-accent font-medium">Auto-Discover</span> to
                    automatically find competitors
                  </span>
                </div>
                <div className="flex items-start gap-2.5 text-[12px] text-text-secondary">
                  <Plus size={12} className="text-accent mt-0.5 flex-shrink-0" />
                  <span>Or type competitor names manually in the field above</span>
                </div>
              </div>

              {/* Actions */}
              <div className="flex items-center gap-2 px-5 py-4 border-t border-border">
                <button
                  onClick={() => {
                    setShowWarn(false)
                    canSubmit && onDiscover(cfg())
                  }}
                  className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded
                             bg-accent text-base text-xs font-medium
                             hover:bg-accent-bright transition-colors"
                >
                  <Search size={12} />
                  Auto-Discover
                </button>
                <button
                  onClick={() => setShowWarn(false)}
                  className="flex-1 py-2 rounded border border-border text-xs
                             text-text-secondary hover:border-border-bright
                             hover:text-text-primary transition-colors"
                >
                  Go Back
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </aside>
  )
}

// ── Internal helpers ──────────────────────────────────────────────────────────

const inputCls = `
  w-full bg-elevated border border-border rounded px-3 py-2 text-sm
  text-text-primary placeholder:text-text-muted font-body outline-none
  focus:border-accent focus:ring-1 focus:ring-accent/20
  disabled:opacity-40 transition-colors
`.replace(/\n\s+/g, ' ').trim()

function Hint({ children }: { children: React.ReactNode }) {
  return <p className="mt-1.5 text-[11px] text-text-muted leading-relaxed">{children}</p>
}

function Label({
  children,
  optional,
  tooltip,
  inline,
}: {
  children: React.ReactNode
  optional?: boolean
  tooltip?: React.ReactNode
  inline?: boolean
}) {
  const base = 'font-mono text-[10px] uppercase tracking-widest text-text-muted'
  if (inline) return <span className={base}>{children}</span>
  return (
    <div className="flex items-center gap-1.5 mb-2">
      <span className={base}>{children}</span>
      {tooltip && <Tooltip content={tooltip} />}
      {optional && <span className="text-[10px] text-text-muted italic ml-auto">optional</span>}
    </div>
  )
}

function Tooltip({ content }: { content: React.ReactNode }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="relative inline-flex">
      <button
        type="button"
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        tabIndex={-1}
        className="w-3.5 h-3.5 rounded-full border border-text-muted/40 text-text-muted
                   flex items-center justify-center text-[9px] font-mono font-bold
                   hover:border-accent hover:text-accent transition-colors cursor-help"
      >
        ?
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 4 }}
            transition={{ duration: 0.15 }}
            className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-60
                       bg-base border border-border rounded p-3 z-50 shadow-xl"
          >
            {content}
            <div className="absolute top-full left-1/2 -translate-x-1/2
                            border-4 border-transparent border-t-border" />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
