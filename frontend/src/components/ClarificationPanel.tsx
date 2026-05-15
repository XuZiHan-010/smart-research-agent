import { useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { Plus, X } from 'lucide-react'
import {
  ClarificationQuestionnaire,
  ConfirmScopePayload,
  DEPTH_CONFIG,
  ResearchConfig,
  ResearchDepth,
} from '../types'

interface Props {
  questionnaire: ClarificationQuestionnaire
  config: ResearchConfig
  onConfirm: (payload: ConfirmScopePayload) => void
  onCancel: () => void
}

const DEPTH_OPTIONS: ResearchDepth[] = ['snapshot', 'standard', 'deep_dive']

export function ClarificationPanel({ questionnaire, config, onConfirm, onCancel }: Props) {
  const [themes, setThemes] = useState(() => Object.fromEntries(questionnaire.themes.map(t => [t.key, t.checked])))
  const [themeDepths, setThemeDepths] = useState<Record<string, ResearchDepth>>(() =>
    Object.fromEntries(questionnaire.themes.map(t => [t.key, config.depth]))
  )
  const [geography, setGeography] = useState(() => Object.fromEntries(questionnaire.geography_options.map(g => [g.key, g.checked])))
  const [timeRange, setTimeRange] = useState(questionnaire.time_range)
  const [customThemes, setCustomThemes] = useState<string[]>([])
  const [customInput, setCustomInput] = useState('')

  const selectedThemes = useMemo(() => Object.entries(themes).filter(([, checked]) => checked).map(([key]) => key), [themes])
  const selectedGeo = useMemo(() => Object.entries(geography).filter(([, checked]) => checked).map(([key]) => key), [geography])
  const canConfirm = (selectedThemes.length + customThemes.length) > 0 && selectedGeo.length > 0 && timeRange.start < timeRange.end

  const addCustom = () => {
    const name = customInput.trim()
    const defaultLabels = new Set(questionnaire.themes.map(t => t.label_zh))
    if (name.length < 2 || name.length > 30 || customThemes.length >= questionnaire.custom_themes_max || defaultLabels.has(name) || customThemes.includes(name)) return
    const key = `custom_${customThemes.length + 1}`
    setCustomThemes(prev => [...prev, name])
    setThemeDepths(prev => ({ ...prev, [key]: config.depth }))
    setCustomInput('')
  }

  const removeCustom = (idx: number) => {
    const nextCustomThemes = customThemes.filter((_, currentIdx) => currentIdx !== idx)
    setCustomThemes(nextCustomThemes)
    setThemeDepths(prev => {
      const next = { ...prev }
      customThemes.forEach((_, currentIdx) => {
        delete next[`custom_${currentIdx + 1}`]
      })
      nextCustomThemes.forEach((_, currentIdx) => {
        const oldIdx = currentIdx >= idx ? currentIdx + 1 : currentIdx
        next[`custom_${currentIdx + 1}`] = prev[`custom_${oldIdx + 1}`] ?? config.depth
      })
      return next
    })
  }

  const setThemeDepth = (key: string, depth: ResearchDepth) => {
    setThemeDepths(prev => ({ ...prev, [key]: depth }))
  }

  const submit = () => {
    if (!canConfirm) return
    const selectedDepths: Record<string, ResearchDepth> = {}
    selectedThemes.forEach(key => {
      selectedDepths[key] = themeDepths[key] ?? config.depth
    })
    customThemes.forEach((_, idx) => {
      const key = `custom_${idx + 1}`
      selectedDepths[key] = themeDepths[key] ?? config.depth
    })

    onConfirm({
      clarification_id: questionnaire.clarification_id,
      selected_themes: selectedThemes,
      custom_themes: customThemes,
      geography: selectedGeo,
      time_range: timeRange,
      depth: config.depth,
      theme_depths: selectedDepths,
    })
  }

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
      <motion.div initial={{ scale: 0.96, y: 12 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.96, y: 12 }} className="w-full max-w-3xl max-h-[88vh] overflow-y-auto bg-surface border border-border rounded shadow-2xl">
        <div className="flex items-start justify-between gap-4 px-6 py-5 border-b border-border">
          <div>
            <span className="font-mono text-[10px] uppercase tracking-widest text-accent">Scope Questionnaire</span>
            <h2 className="mt-2 text-xl font-display text-text-primary">{questionnaire.research_domain}</h2>
          </div>
          <button onClick={onCancel} className="text-text-muted hover:text-text-primary"><X size={18} /></button>
        </div>

        <div className="p-6 space-y-6">
          <section>
            <Label>研究主题</Label>
            <div className="grid gap-2">
              {questionnaire.themes.map(theme => (
                <div key={theme.key} className="flex items-center gap-3 border border-border bg-elevated rounded px-3 py-2 text-sm text-text-secondary">
                  <label className="flex min-w-0 flex-1 items-center gap-3">
                    <input type="checkbox" checked={!!themes[theme.key]} onChange={e => setThemes(prev => ({ ...prev, [theme.key]: e.target.checked }))} />
                    <span className="min-w-0 flex-1">{theme.label_zh}</span>
                  </label>
                  <DepthControl value={themeDepths[theme.key] ?? config.depth} onChange={depth => setThemeDepth(theme.key, depth)} disabled={!themes[theme.key]} />
                </div>
              ))}
            </div>
          </section>

          <section>
            <Label>自定义主题</Label>
            <div className="flex gap-2">
              <input value={customInput} onChange={e => setCustomInput(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addCustom() } }} placeholder="例如 ESG与可持续发展" className={inputCls} />
              <button type="button" onClick={addCustom} disabled={customThemes.length >= questionnaire.custom_themes_max} className="px-3 rounded border border-border text-text-secondary hover:border-accent hover:text-accent disabled:opacity-30">
                <Plus size={15} />
              </button>
            </div>
            <div className="space-y-2 mt-2">
              {customThemes.map((theme, idx) => {
                const key = `custom_${idx + 1}`
                return (
                  <div key={`${key}:${theme}`} className="flex items-center gap-3 border border-accent/30 bg-accent/10 rounded px-3 py-2 text-sm text-accent">
                    <span className="min-w-0 flex-1">{theme}</span>
                    <DepthControl value={themeDepths[key] ?? config.depth} onChange={depth => setThemeDepth(key, depth)} />
                    <button onClick={() => removeCustom(idx)}><X size={13} /></button>
                  </div>
                )
              })}
            </div>
          </section>

          <section>
            <Label>地理范围</Label>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              {questionnaire.geography_options.map(option => (
                <label key={option.key} className="flex items-center gap-2 border border-border bg-elevated rounded px-3 py-2 text-sm text-text-secondary">
                  <input type="checkbox" checked={!!geography[option.key]} onChange={e => setGeography(prev => ({ ...prev, [option.key]: e.target.checked }))} />
                  <span>{option.label_zh}</span>
                </label>
              ))}
            </div>
          </section>

          <section>
            <Label>时间窗口</Label>
            <div className="grid grid-cols-2 gap-3">
              <input type="month" value={timeRange.start} onChange={e => setTimeRange(prev => ({ ...prev, start: e.target.value }))} className={inputCls} />
              <input type="month" value={timeRange.end} onChange={e => setTimeRange(prev => ({ ...prev, end: e.target.value }))} className={inputCls} />
            </div>
          </section>
        </div>

        <div className="px-6 py-4 border-t border-border flex justify-end gap-3">
          <button onClick={onCancel} className="px-4 py-2 rounded border border-border text-sm text-text-secondary hover:text-text-primary">Cancel</button>
          <button onClick={submit} disabled={!canConfirm} className="px-4 py-2 rounded bg-accent text-base text-sm font-medium hover:bg-accent-bright disabled:opacity-30">Confirm & Run</button>
        </div>
      </motion.div>
    </motion.div>
  )
}

function DepthControl({ value, onChange, disabled = false }: { value: ResearchDepth; onChange: (depth: ResearchDepth) => void; disabled?: boolean }) {
  return (
    <div className="grid w-56 grid-cols-3 gap-px overflow-hidden rounded border border-border bg-border">
      {DEPTH_OPTIONS.map(depth => (
        <button
          key={depth}
          type="button"
          disabled={disabled}
          onClick={() => onChange(depth)}
          className={`flex flex-col items-center gap-0.5 py-2 px-2 transition-colors disabled:opacity-30 ${value === depth ? 'bg-accent/10 text-accent' : 'bg-surface text-text-muted hover:text-text-primary'}`}
        >
          <span className="text-xs font-medium">{DEPTH_CONFIG[depth].label}</span>
          <span className="font-mono text-[9px]">{DEPTH_CONFIG[depth].estimate}</span>
        </button>
      ))}
    </div>
  )
}

const inputCls = 'w-full bg-elevated border border-border rounded px-3 py-2 text-sm text-text-primary placeholder:text-text-muted outline-none focus:border-accent focus:ring-1 focus:ring-accent/20'
function Label({ children }: { children: React.ReactNode }) {
  return <div className="font-mono text-[10px] uppercase tracking-widest text-text-muted mb-2">{children}</div>
}
