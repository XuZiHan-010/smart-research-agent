import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Check, X, Plus, Loader2 } from 'lucide-react'
import { DiscoverySuggestion, CompanyInput, ResearchConfig } from '../types'

interface Props {
  config:      ResearchConfig
  suggestions: DiscoverySuggestion[]
  isLoading:   boolean
  onConfirm:   (config: ResearchConfig, companies: CompanyInput[]) => void
  onCancel:    () => void
}

export function DiscoveryPanel({ config, suggestions, isLoading, onConfirm, onCancel }: Props) {
  // Pre-check all suggestions that had default_checked=true
  const [checked, setChecked] = useState<Record<string, boolean>>(
    Object.fromEntries(suggestions.map(s => [s.name, s.default_checked]))
  )
  const [manualName,    setManualName]    = useState('')
  const [manualWebsite, setManualWebsite] = useState('')
  const [manualList,    setManualList]    = useState<{ name: string; website: string }[]>(
    config.competitorNames.map(n => ({ name: n, website: '' }))
  )

  const toggleSuggestion = (name: string) =>
    setChecked(prev => ({ ...prev, [name]: !prev[name] }))

  const addManual = () => {
    const name = manualName.trim()
    if (!name) return
    const already = manualList.some(m => m.name.toLowerCase() === name.toLowerCase())
    if (already) return
    setManualList(prev => [...prev, { name, website: manualWebsite.trim() }])
    setManualName('')
    setManualWebsite('')
  }

  const removeManual = (name: string) =>
    setManualList(prev => prev.filter(m => m.name !== name))

  const handleConfirm = () => {
    const companies: CompanyInput[] = [
      // Target company first
      { name: config.target_company, website: config.target_website, source: 'target' },
      // Manual entries (user-provided before discovery)
      ...manualList.map(m => ({ name: m.name, website: m.website, source: 'user' as const })),
      // Checked suggestions
      ...suggestions
        .filter(s => checked[s.name])
        .map(s => ({ name: s.name, website: s.website, source: 'discovered' as const })),
    ]
    onConfirm(config, companies)
  }

  const totalCompetitors =
    manualList.length + suggestions.filter(s => checked[s.name]).length

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
    >
      <motion.div
        initial={{ scale: 0.95, y: 16 }}
        animate={{ scale: 1, y: 0 }}
        exit={{ scale: 0.95, y: 16 }}
        className="bg-surface border border-border rounded-lg w-full max-w-lg
                   flex flex-col max-h-[85vh] shadow-2xl"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border flex-shrink-0">
          <div>
            <h2 className="font-display text-lg font-light text-text-primary">
              Competitor Discovery
            </h2>
            <p className="font-mono text-[11px] text-text-muted mt-0.5">
              for <span className="text-accent">{config.target_company}</span>
            </p>
          </div>
          <button onClick={onCancel} className="text-text-muted hover:text-text-primary transition-colors">
            <X size={16} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">

          {/* Loading state */}
          {isLoading && (
            <div className="flex items-center gap-3 text-text-secondary font-mono text-sm">
              <Loader2 size={14} className="animate-spin text-accent" />
              Searching for competitors…
            </div>
          )}

          {/* Discovered suggestions */}
          {!isLoading && suggestions.length > 0 && (
            <section>
              <h3 className="font-mono text-[10px] uppercase tracking-widest text-text-muted mb-3">
                Auto-Discovered ({suggestions.length})
              </h3>
              <div className="space-y-2">
                {suggestions.map(s => (
                  <button
                    key={s.name}
                    type="button"
                    onClick={() => toggleSuggestion(s.name)}
                    className={`w-full flex items-center gap-3 px-3 py-2.5 rounded border
                      text-left transition-all duration-150
                      ${checked[s.name]
                        ? 'border-accent/50 bg-accent/5'
                        : 'border-border bg-elevated hover:border-border-bright'
                      }`}
                  >
                    {/* Checkbox */}
                    <span className={`w-4 h-4 rounded border flex-shrink-0 flex items-center justify-center
                      ${checked[s.name] ? 'border-accent bg-accent' : 'border-border-bright bg-transparent'}`}>
                      {checked[s.name] && <Check size={10} className="text-base" />}
                    </span>

                    <div className="flex-1 min-w-0">
                      <span className={`text-sm font-medium block truncate
                        ${checked[s.name] ? 'text-text-primary' : 'text-text-secondary'}`}>
                        {s.name}
                      </span>
                      {s.website && (
                        <span className="text-[11px] text-text-muted font-mono truncate block">
                          {s.website.replace(/^https?:\/\//, '')}
                        </span>
                      )}
                      {s.reason && (
                        <span className="text-[10px] text-text-muted/70 block mt-0.5 line-clamp-1">
                          {s.reason}
                        </span>
                      )}
                    </div>

                    {/* Relevance score */}
                    <span className="font-mono text-[10px] text-text-muted flex-shrink-0">
                      {Math.round(s.score * 100)}%
                    </span>
                  </button>
                ))}
              </div>
            </section>
          )}

          {!isLoading && suggestions.length === 0 && (
            <p className="text-sm text-text-muted font-mono">
              No suggestions found. Add competitors manually below.
            </p>
          )}

          {/* Manual entries */}
          <section>
            <h3 className="font-mono text-[10px] uppercase tracking-widest text-text-muted mb-3">
              Manual Entries
            </h3>

            {/* Existing manual list */}
            {manualList.length > 0 && (
              <div className="space-y-1.5 mb-3">
                {manualList.map(m => (
                  <div key={m.name} className="flex items-center gap-2 px-3 py-2 bg-elevated
                                               border border-border rounded text-sm">
                    <span className="flex-1 text-text-primary">{m.name}</span>
                    {m.website && (
                      <span className="text-[11px] text-text-muted font-mono truncate max-w-[120px]">
                        {m.website.replace(/^https?:\/\//, '')}
                      </span>
                    )}
                    <button
                      type="button"
                      onClick={() => removeManual(m.name)}
                      className="text-text-muted hover:text-error-red transition-colors"
                    >
                      <X size={12} />
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* Add manual */}
            <div className="flex gap-2">
              <input
                value={manualName}
                onChange={e => setManualName(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), addManual())}
                placeholder="Company name"
                className="flex-1 bg-elevated border border-border rounded px-3 py-2 text-sm
                           text-text-primary placeholder:text-text-muted outline-none
                           focus:border-accent focus:ring-1 focus:ring-accent/20 transition-colors"
              />
              <input
                value={manualWebsite}
                onChange={e => setManualWebsite(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), addManual())}
                placeholder="URL (optional)"
                className="w-32 bg-elevated border border-border rounded px-3 py-2 text-sm
                           text-text-primary placeholder:text-text-muted outline-none
                           focus:border-accent focus:ring-1 focus:ring-accent/20 transition-colors"
              />
              <button
                type="button"
                onClick={addManual}
                className="flex-shrink-0 p-2 border border-border rounded text-text-secondary
                           hover:border-accent hover:text-accent transition-colors"
              >
                <Plus size={16} />
              </button>
            </div>
          </section>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-border flex items-center justify-between flex-shrink-0">
          <span className="font-mono text-[11px] text-text-muted">
            {totalCompetitors} competitor{totalCompetitors !== 1 ? 's' : ''} selected
          </span>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={onCancel}
              className="px-4 py-2 text-sm font-mono text-text-secondary border border-border
                         rounded hover:border-border-bright hover:text-text-primary transition-colors"
            >
              Back
            </button>
            <button
              type="button"
              onClick={handleConfirm}
              className="px-4 py-2 text-sm font-medium bg-accent text-base rounded
                         hover:bg-accent-bright transition-colors shadow-lg shadow-accent/10"
            >
              Confirm & Start →
            </button>
          </div>
        </div>
      </motion.div>
    </motion.div>
  )
}
