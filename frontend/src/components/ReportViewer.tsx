import { useMemo, useState, Fragment } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import { Check, Copy, Download, ExternalLink, FileText, Link2 } from 'lucide-react'
import clsx from 'clsx'
import { CitationRef } from '../types'

const API = import.meta.env.VITE_API_URL ?? ''

interface Props {
  report:      string
  jobId?:      string | null
  isStreaming?: boolean
  citations?:  Record<number, CitationRef>
}

type Tab = 'report' | 'sources'

// ── Parse legacy "##关键来源清单" markdown table when no structured citations ──
const parseLegacySources = (report: string): { index: number; raw: string }[] => {
  const match = report.match(/##\s*关键来源清单\s*\n([\s\S]+?)(?:\n## |\n#\s|\s*$)/)
  if (!match) return []
  return match[1]
    .split('\n')
    .filter(line => line.trim().startsWith('|') && !line.includes('---'))
    .slice(1)
    .map((raw, i) => ({ index: i + 1, raw }))
}

export function ReportViewer({ report, jobId, isStreaming, citations = {} }: Props) {
  const [tab, setTab] = useState<Tab>('report')
  const [copied, setCopied] = useState(false)
  const [hoverIdx, setHoverIdx] = useState<number | null>(null)

  const hasStructuredCitations = Object.keys(citations).length > 0
  const legacySources = useMemo(() => parseLegacySources(report), [report])

  const copy = () => {
    navigator.clipboard.writeText(report)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const download = async (format: 'markdown' | 'pdf' | 'word') => {
    if (!jobId) return
    const res = await fetch(`${API}/api/research/${jobId}/download?format=${format}`)
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `market-study.${format === 'markdown' ? 'md' : format === 'word' ? 'docx' : 'pdf'}`
    a.click()
    URL.revokeObjectURL(url)
  }

  // Render text replacing [N] with interactive citation chip
  const renderTextWithCitations = (text: string, keyPrefix: string) => {
    const regex = /\[(\d+)\]/g
    const parts: React.ReactNode[] = []
    let lastIdx = 0
    let m: RegExpExecArray | null
    let i = 0
    while ((m = regex.exec(text)) !== null) {
      if (m.index > lastIdx) parts.push(text.slice(lastIdx, m.index))
      const idx = parseInt(m[1], 10)
      const cite = citations[idx]
      parts.push(
        <span key={`${keyPrefix}-${i++}`} className="relative inline-block">
          <sup
            onMouseEnter={() => setHoverIdx(idx)}
            onMouseLeave={() => setHoverIdx(null)}
            className={clsx(
              'cursor-pointer mx-0.5 px-1 py-0.5 rounded-sm font-mono text-[10px] transition-all',
              cite
                ? 'text-accent border-b border-dotted border-accent/40 hover:bg-accent/15 hover:text-accent-bright'
                : 'text-accent/60 border-b border-dotted border-accent/20',
            )}
          >
            {idx}
          </sup>
          {hoverIdx === idx && cite && (
            <CitationCard citation={cite} />
          )}
        </span>
      )
      lastIdx = regex.lastIndex
    }
    if (lastIdx < text.length) parts.push(text.slice(lastIdx))
    return parts.length > 0 ? <>{parts.map((p, idx) => <Fragment key={idx}>{p}</Fragment>)}</> : text
  }

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col h-full">
      <div className="flex items-center justify-between pb-3 border-b border-border mb-4 flex-shrink-0 gap-3">
        <div className="flex items-center gap-1">
          <TabBtn active={tab === 'report'} onClick={() => setTab('report')}>
            <FileText size={12} /> Report
          </TabBtn>
          <TabBtn
            active={tab === 'sources'}
            onClick={() => setTab('sources')}
            disabled={!hasStructuredCitations && !legacySources.length}
          >
            <Link2 size={12} />
            Sources
            {hasStructuredCitations && (
              <span className="font-mono text-[9px] text-accent ml-1">{Object.keys(citations).length}</span>
            )}
          </TabBtn>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          {isStreaming && (
            <span className="font-mono text-[10px] text-accent flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
              generating
            </span>
          )}
          <ActionBtn onClick={copy} title="Copy markdown">
            {copied ? <Check size={12} className="text-active-green" /> : <Copy size={12} />}
            <span>{copied ? 'Copied' : 'Copy'}</span>
          </ActionBtn>
          {jobId && (
            <>
              <ActionBtn onClick={() => download('markdown')} title="Download MD"><Download size={12} /><span>MD</span></ActionBtn>
              <ActionBtn onClick={() => download('pdf')} title="Download PDF"><Download size={12} /><span>PDF</span></ActionBtn>
              <ActionBtn onClick={() => download('word')} title="Download Word"><Download size={12} /><span>Word</span></ActionBtn>
            </>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {tab === 'report' && (
          <div className="prose prose-invert prose-sm max-w-none
                          prose-headings:font-display prose-headings:font-light
                          prose-headings:text-text-primary
                          prose-h1:text-2xl prose-h2:text-xl prose-h2:border-b
                          prose-h2:border-border prose-h2:pb-2
                          prose-p:text-text-secondary prose-p:leading-relaxed
                          prose-li:text-text-secondary prose-table:text-text-secondary
                          prose-th:text-text-primary prose-td:border-border prose-th:border-border
                          prose-strong:text-text-primary prose-strong:font-medium
                          prose-code:text-accent prose-code:bg-elevated prose-code:px-1
                          prose-code:rounded prose-code:text-xs
                          prose-a:text-accent prose-a:no-underline hover:prose-a:underline
                          prose-blockquote:border-l-accent prose-blockquote:text-text-muted">
            <ReactMarkdown
              components={hasStructuredCitations ? {
                p: ({ children }) => (
                  <p>{processChildren(children, renderTextWithCitations)}</p>
                ),
                li: ({ children }) => (
                  <li>{processChildren(children, renderTextWithCitations)}</li>
                ),
                td: ({ children }) => (
                  <td>{processChildren(children, renderTextWithCitations)}</td>
                ),
              } : undefined}
            >
              {report}
            </ReactMarkdown>
            {isStreaming && <span className="inline-block text-accent animate-blink">▌</span>}
          </div>
        )}

        {tab === 'sources' && (
          <div className="space-y-2">
            <p className="font-mono text-[10px] uppercase tracking-widest text-text-muted mb-4">
              {hasStructuredCitations ? Object.keys(citations).length : legacySources.length} sources
            </p>

            {hasStructuredCitations ? (
              <div className="grid gap-2">
                {Object.values(citations)
                  .sort((a, b) => a.index - b.index)
                  .map(c => <SourceCard key={c.index} citation={c} />)}
              </div>
            ) : (
              legacySources.map(s => (
                <div key={s.index} className="text-xs text-text-secondary border border-border rounded bg-elevated p-3">
                  {s.raw}
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </motion.div>
  )
}

// ── Source card (Sources tab) ────────────────────────────────────────────────
function SourceCard({ citation }: { citation: CitationRef }) {
  let hostname = ''
  try { hostname = new URL(citation.url).hostname.replace(/^www\./, '') } catch { hostname = citation.url }
  return (
    <a
      href={citation.url}
      target="_blank"
      rel="noopener noreferrer"
      className="group block border border-border bg-elevated rounded p-4 hover:border-accent/40 transition-colors"
    >
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="flex items-center gap-2">
          <span className="font-mono text-[10px] text-accent tabular-nums px-1.5 py-0.5 rounded bg-accent/10 border border-accent/30">
            [{citation.index}]
          </span>
          <span className="font-mono text-[10px] uppercase tracking-widest text-text-muted">
            {hostname}
            {citation.published && ` · ${citation.published}`}
          </span>
        </div>
        <ExternalLink size={12} className="text-text-muted group-hover:text-accent flex-shrink-0" />
      </div>
      <h4 className="font-display text-base text-text-primary leading-snug group-hover:text-accent transition-colors">
        {citation.title}
      </h4>
      {citation.excerpt && (
        <p className="text-xs text-text-secondary mt-2 leading-relaxed line-clamp-3">
          {citation.excerpt}
        </p>
      )}
    </a>
  )
}

// ── Hover card for inline citation ───────────────────────────────────────────
function CitationCard({ citation }: { citation: CitationRef }) {
  let hostname = ''
  try { hostname = new URL(citation.url).hostname.replace(/^www\./, '') } catch { hostname = citation.url }
  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: -4 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.12 }}
        className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-80 z-30
                   bg-elevated border border-accent/30 rounded p-3 shadow-2xl
                   pointer-events-auto"
      >
        <div className="flex items-center gap-2 mb-1.5">
          <span className="font-mono text-[9px] text-accent uppercase tracking-widest">
            Source [{citation.index}]
          </span>
          <span className="font-mono text-[9px] text-text-muted">
            {hostname}{citation.published && ` · ${citation.published}`}
          </span>
        </div>
        <h4 className="font-display text-base text-text-primary leading-snug">
          {citation.title}
        </h4>
        {citation.excerpt && (
          <p className="text-text-secondary text-xs mt-2 leading-relaxed line-clamp-3 italic">
            "{citation.excerpt}"
          </p>
        )}
        <a
          href={citation.url}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-2 flex items-center gap-1.5 text-accent text-xs hover:text-accent-bright"
        >
          <span>open source</span>
          <ExternalLink size={10} />
        </a>
      </motion.div>
    </AnimatePresence>
  )
}

// ── helpers ──────────────────────────────────────────────────────────────────
function processChildren(
  children: React.ReactNode,
  renderText: (s: string, key: string) => React.ReactNode,
): React.ReactNode {
  if (typeof children === 'string') return renderText(children, 'r')
  if (Array.isArray(children)) {
    return children.map((c, i) =>
      typeof c === 'string'
        ? <Fragment key={i}>{renderText(c, `r${i}`)}</Fragment>
        : <Fragment key={i}>{c}</Fragment>
    )
  }
  return children
}

function TabBtn({ children, active, onClick, disabled }: {
  children: React.ReactNode
  active: boolean
  onClick: () => void
  disabled?: boolean
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-mono rounded transition-colors disabled:opacity-30 disabled:cursor-not-allowed
        ${active ? 'bg-accent/10 text-accent border border-accent/30' : 'text-text-secondary border border-transparent hover:border-border hover:text-text-primary'}`}
    >
      {children}
    </button>
  )
}

function ActionBtn({ children, onClick, title }: {
  children: React.ReactNode
  onClick: () => void
  title?: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      className="flex items-center gap-1.5 px-2.5 py-1.5 rounded border border-border text-text-secondary text-xs font-mono hover:border-border-bright hover:text-text-primary transition-colors"
    >
      {children}
    </button>
  )
}
