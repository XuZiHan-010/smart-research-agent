import { useState } from 'react'
import { motion } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import { Copy, Download, Check, FileText, LayoutGrid, Link2, Edit3, X } from 'lucide-react'
import { BattlecardData } from '../types'
import { BattlecardView } from './BattlecardView'

const API = import.meta.env.VITE_API_URL ?? ''

interface Props {
  report:      string
  jobId?:      string | null
  isStreaming?: boolean
  battlecard?: BattlecardData | null
  onEdit?:     (mode: 'quick_edit' | 'targeted_refresh' | 'full_refresh', instruction: string) => void
}

type Tab = 'report' | 'battlecard' | 'sources'

export function ReportViewer({ report, jobId, isStreaming, battlecard, onEdit }: Props) {
  const [tab,     setTab]     = useState<Tab>('report')
  const [copied,  setCopied]  = useState(false)
  const [editing, setEditing] = useState(false)
  const [editMode, setEditMode] = useState<'quick_edit' | 'targeted_refresh' | 'full_refresh'>('quick_edit')
  const [editInstruction, setEditInstruction] = useState('')

  // Extract sources section from markdown
  const sourcesMatch = report.match(/## Sources\s*\n([\s\S]+?)(?:\n## |\n#\s|\s*$)/)
  const sourcesText  = sourcesMatch ? sourcesMatch[1].trim() : ''
  const sourceLines  = sourcesText
    ? sourcesText.split('\n').filter(l => l.trim()).map(l => l.replace(/^\d+\.\s*/, ''))
    : []

  const copy = () => {
    navigator.clipboard.writeText(report)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const download = async (format: 'markdown' | 'pdf' | 'json') => {
    if (!jobId) return
    const res  = await fetch(`${API}/api/research/${jobId}/download?format=${format}`)
    const blob = await res.blob()
    const url  = URL.createObjectURL(blob)
    const a    = document.createElement('a')
    a.href     = url
    a.download = `report.${format === 'markdown' ? 'md' : format}`
    a.click()
    URL.revokeObjectURL(url)
  }

  const submitEdit = () => {
    if (!editInstruction.trim() || !onEdit) return
    onEdit(editMode, editInstruction.trim())
    setEditing(false)
    setEditInstruction('')
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="flex flex-col h-full"
    >
      {/* Toolbar */}
      <div className="flex items-center justify-between pb-3 border-b border-border mb-4 flex-shrink-0 gap-3">
        {/* Tabs */}
        <div className="flex items-center gap-1">
          <TabBtn active={tab === 'report'} onClick={() => setTab('report')}>
            <FileText size={12} /> Report
          </TabBtn>
          <TabBtn active={tab === 'battlecard'} onClick={() => setTab('battlecard')} disabled={!battlecard}>
            <LayoutGrid size={12} /> Battlecard
          </TabBtn>
          <TabBtn active={tab === 'sources'} onClick={() => setTab('sources')} disabled={!sourceLines.length}>
            <Link2 size={12} /> Sources
          </TabBtn>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 flex-shrink-0">
          {isStreaming && (
            <span className="font-mono text-[10px] text-accent animate-pulse">generating…</span>
          )}

          {onEdit && !isStreaming && (
            <ActionBtn onClick={() => setEditing(v => !v)} title="Edit report">
              <Edit3 size={12} /> Edit
            </ActionBtn>
          )}

          <ActionBtn onClick={copy} title="Copy markdown">
            {copied ? <Check size={12} className="text-active-green" /> : <Copy size={12} />}
            <span>{copied ? 'Copied' : 'Copy'}</span>
          </ActionBtn>

          {jobId && (
            <>
              <ActionBtn onClick={() => download('markdown')} title="Download MD">
                <Download size={12} /><span>MD</span>
              </ActionBtn>
              <ActionBtn onClick={() => download('pdf')} title="Download PDF">
                <Download size={12} /><span>PDF</span>
              </ActionBtn>
              <ActionBtn onClick={() => download('json')} title="Download JSON">
                <Download size={12} /><span>JSON</span>
              </ActionBtn>
            </>
          )}
        </div>
      </div>

      {/* Edit panel */}
      {editing && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: 'auto' }}
          exit={{ opacity: 0, height: 0 }}
          className="mb-4 border border-accent/30 rounded bg-accent/5 p-4 flex-shrink-0"
        >
          <div className="flex items-center justify-between mb-3">
            <span className="font-mono text-[10px] uppercase tracking-widest text-accent">Edit Report</span>
            <button onClick={() => setEditing(false)} className="text-text-muted hover:text-text-primary">
              <X size={13} />
            </button>
          </div>

          {/* Edit mode selector */}
          <div className="flex gap-2 mb-3">
            {(['quick_edit', 'targeted_refresh', 'full_refresh'] as const).map(m => (
              <button
                key={m}
                type="button"
                onClick={() => setEditMode(m)}
                className={`px-3 py-1.5 text-xs font-mono rounded border transition-colors
                  ${editMode === m
                    ? 'border-accent bg-accent/10 text-accent'
                    : 'border-border bg-elevated text-text-secondary hover:border-border-bright'
                  }`}
              >
                {m === 'quick_edit' ? 'Quick Edit' :
                 m === 'targeted_refresh' ? 'Targeted Refresh' : 'Full Refresh'}
              </button>
            ))}
          </div>

          <p className="text-[11px] text-text-muted mb-3 font-mono">
            {editMode === 'quick_edit' && 'Applies your instruction to the existing text. No new research.'}
            {editMode === 'targeted_refresh' && 'Rewrites only sections with new research data.'}
            {editMode === 'full_refresh' && 'Runs the full pipeline and rewrites the entire report.'}
          </p>

          <textarea
            value={editInstruction}
            onChange={e => setEditInstruction(e.target.value)}
            placeholder="e.g. Make the Executive Summary shorter, add a risk matrix, focus more on pricing…"
            rows={3}
            className="w-full bg-elevated border border-border rounded px-3 py-2 text-sm
                       text-text-primary placeholder:text-text-muted font-body outline-none
                       focus:border-accent focus:ring-1 focus:ring-accent/20 resize-none
                       transition-colors leading-relaxed"
          />

          <div className="flex justify-end mt-3">
            <button
              type="button"
              onClick={submitEdit}
              disabled={!editInstruction.trim()}
              className="px-4 py-2 text-sm font-medium bg-accent text-base rounded
                         hover:bg-accent-bright disabled:opacity-30 disabled:cursor-not-allowed
                         transition-colors"
            >
              Apply Edit →
            </button>
          </div>
        </motion.div>
      )}

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {tab === 'report' && (
          <div className="prose prose-invert prose-sm max-w-none
                          prose-headings:font-display prose-headings:font-light
                          prose-headings:text-text-primary
                          prose-h1:text-2xl prose-h2:text-xl prose-h2:border-b
                          prose-h2:border-border prose-h2:pb-2
                          prose-p:text-text-secondary prose-p:leading-relaxed
                          prose-li:text-text-secondary
                          prose-strong:text-text-primary prose-strong:font-medium
                          prose-code:text-accent prose-code:bg-elevated prose-code:px-1
                          prose-code:rounded prose-code:text-xs
                          prose-a:text-accent prose-a:no-underline hover:prose-a:underline
                          prose-blockquote:border-l-accent prose-blockquote:text-text-muted">
            <ReactMarkdown>{report}</ReactMarkdown>
            {isStreaming && <span className="inline-block text-accent animate-blink">▌</span>}
          </div>
        )}

        {tab === 'battlecard' && battlecard && (
          <BattlecardView battlecard={battlecard} />
        )}

        {tab === 'sources' && (
          <div className="space-y-2">
            <p className="font-mono text-[10px] uppercase tracking-widest text-text-muted mb-4">
              {sourceLines.length} source{sourceLines.length !== 1 ? 's' : ''}
            </p>
            {sourceLines.map((url, i) => (
              <div key={i} className="flex items-center gap-3 text-xs font-mono">
                <span className="text-text-muted w-6 text-right flex-shrink-0">{i + 1}.</span>
                <a
                  href={url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-accent hover:underline truncate"
                >
                  {url}
                </a>
              </div>
            ))}
          </div>
        )}
      </div>
    </motion.div>
  )
}

// ── Internal helpers ──────────────────────────────────────────────────────────

function TabBtn({ children, active, onClick, disabled }: {
  children: React.ReactNode
  active:   boolean
  onClick:  () => void
  disabled?: boolean
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-mono rounded transition-colors
        disabled:opacity-30 disabled:cursor-not-allowed
        ${active
          ? 'bg-accent/10 text-accent border border-accent/30'
          : 'text-text-secondary border border-transparent hover:border-border hover:text-text-primary'
        }`}
    >
      {children}
    </button>
  )
}

function ActionBtn({ children, onClick, title }: {
  children: React.ReactNode
  onClick:  () => void
  title?:   string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      className="flex items-center gap-1.5 px-2.5 py-1.5 rounded border border-border
                 text-text-secondary text-xs font-mono
                 hover:border-border-bright hover:text-text-primary transition-colors"
    >
      {children}
    </button>
  )
}
