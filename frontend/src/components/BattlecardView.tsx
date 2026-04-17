import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { BattlecardData } from '../types'

interface Props {
  battlecard: BattlecardData
}

export function BattlecardView({ battlecard }: Props) {
  if (battlecard.parse_error) {
    return (
      <div className="p-6 text-center font-mono text-sm text-text-muted">
        <p className="text-error-red mb-2">Battlecard parse error</p>
        <p className="text-xs">{battlecard.parse_error}</p>
      </div>
    )
  }

  return (
    <div className="space-y-6 p-1">

      {/* Companies header */}
      <div className="flex items-center gap-3 flex-wrap">
        <span className="px-2.5 py-1 bg-accent/10 border border-accent/30 rounded text-xs font-mono text-accent">
          ★ {battlecard.target}
        </span>
        {battlecard.competitors?.map(c => (
          <span key={c} className="px-2.5 py-1 bg-elevated border border-border rounded text-xs font-mono text-text-secondary">
            {c}
          </span>
        ))}
      </div>

      {/* Feature Matrix */}
      {battlecard.feature_matrix?.length > 0 && (
        <section>
          <SectionTitle>Feature Matrix</SectionTitle>
          <div className="overflow-x-auto rounded border border-border">
            <table className="w-full text-xs font-mono border-collapse">
              <thead>
                <tr className="border-b border-border bg-elevated">
                  <th className="text-left px-3 py-2 text-text-muted font-normal w-40">Feature</th>
                  {[battlecard.target, ...(battlecard.competitors ?? [])].map(c => (
                    <th key={c} className="px-3 py-2 text-center text-text-muted font-normal">
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {battlecard.feature_matrix.map((row, i) => (
                  <tr key={i} className={`border-b border-border ${i % 2 === 0 ? 'bg-surface' : 'bg-elevated'}`}>
                    <td className="px-3 py-2 text-text-secondary">{row.feature}</td>
                    {[battlecard.target, ...(battlecard.competitors ?? [])].map(c => {
                      const val = row.companies?.[c] ?? 'unknown'
                      return (
                        <td key={c} className="px-3 py-2 text-center">
                          <FeatureCell value={val} />
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Pricing Comparison */}
      {battlecard.pricing_comparison?.length > 0 && (
        <section>
          <SectionTitle>Pricing</SectionTitle>
          <div className="overflow-x-auto rounded border border-border">
            <table className="w-full text-xs font-mono border-collapse">
              <thead>
                <tr className="border-b border-border bg-elevated">
                  <th className="text-left px-3 py-2 text-text-muted font-normal">Company</th>
                  <th className="text-left px-3 py-2 text-text-muted font-normal">Model</th>
                  <th className="text-left px-3 py-2 text-text-muted font-normal">Entry Price</th>
                  <th className="text-left px-3 py-2 text-text-muted font-normal">Enterprise</th>
                </tr>
              </thead>
              <tbody>
                {battlecard.pricing_comparison.map((row, i) => (
                  <tr key={i} className={`border-b border-border ${i % 2 === 0 ? 'bg-surface' : 'bg-elevated'}`}>
                    <td className="px-3 py-2 text-text-primary font-medium">{row.company}</td>
                    <td className="px-3 py-2 text-text-secondary capitalize">{row.model ?? '—'}</td>
                    <td className="px-3 py-2 text-text-secondary">{row.entry_price ?? '—'}</td>
                    <td className="px-3 py-2 text-text-muted">{row.enterprise ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Win / Lose Themes side by side */}
      <div className="grid grid-cols-2 gap-4">
        {battlecard.win_themes?.length > 0 && (
          <section>
            <SectionTitle className="text-active-green">Win Themes</SectionTitle>
            <div className="space-y-2">
              {battlecard.win_themes.map((w, i) => (
                <ThemeCard
                  key={i}
                  vs={w.vs_competitor}
                  theme={w.theme}
                  evidence={w.evidence}
                  type="win"
                />
              ))}
            </div>
          </section>
        )}

        {battlecard.lose_themes?.length > 0 && (
          <section>
            <SectionTitle className="text-error-red">Areas to Address</SectionTitle>
            <div className="space-y-2">
              {battlecard.lose_themes.map((l, i) => (
                <ThemeCard
                  key={i}
                  vs={l.vs_competitor}
                  theme={l.theme}
                  evidence={l.evidence}
                  type="lose"
                />
              ))}
            </div>
          </section>
        )}
      </div>

      {/* Key Risks */}
      {battlecard.key_risks?.length > 0 && (
        <section>
          <SectionTitle>Key Risks</SectionTitle>
          <ul className="space-y-1.5">
            {battlecard.key_risks.map((r, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-text-secondary">
                <span className="text-error-red mt-0.5 flex-shrink-0">▸</span>
                {r}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Objection Handlers */}
      {battlecard.objection_handlers?.length > 0 && (
        <section>
          <SectionTitle>Objection Handlers</SectionTitle>
          <div className="space-y-2">
            {battlecard.objection_handlers.map((o, i) => (
              <ObjectionCard key={i} objection={o.objection} response={o.response} />
            ))}
          </div>
        </section>
      )}

      {/* Footer */}
      <p className="font-mono text-[10px] text-text-muted text-right">
        Generated {new Date(battlecard.generated_at).toLocaleDateString()}
      </p>
    </div>
  )
}

// ── Sub-components ────────────────────────────────────────────────────────────

function SectionTitle({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <h3 className={`font-mono text-[10px] uppercase tracking-widest mb-3 ${className || 'text-text-muted'}`}>
      {children}
    </h3>
  )
}

function FeatureCell({ value }: { value: string }) {
  const map: Record<string, { icon: string; cls: string }> = {
    yes:     { icon: '✓', cls: 'text-active-green' },
    partial: { icon: '◑', cls: 'text-yellow-400' },
    no:      { icon: '✗', cls: 'text-error-red/60' },
    unknown: { icon: '—', cls: 'text-text-muted' },
  }
  const { icon, cls } = map[value] ?? map['unknown']
  return <span className={`font-mono font-bold ${cls}`}>{icon}</span>
}

function ThemeCard({ vs, theme, evidence, type }: {
  vs: string; theme: string; evidence: string; type: 'win' | 'lose'
}) {
  const [open, setOpen] = useState(false)
  return (
    <div className={`border rounded p-2.5 text-xs
      ${type === 'win' ? 'border-active-green/20 bg-active-green/5' : 'border-error-red/20 bg-error-red/5'}`}
    >
      <button
        type="button"
        onClick={() => setOpen(v => !v)}
        className="w-full text-left flex items-start gap-2"
      >
        <span className="flex-shrink-0 mt-0.5 text-text-muted">
          {open ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
        </span>
        <div className="flex-1">
          <span className="font-mono text-[10px] text-text-muted">vs {vs} · </span>
          <span className="text-text-primary">{theme}</span>
        </div>
      </button>
      {open && evidence && (
        <p className="mt-2 pl-5 text-text-secondary leading-relaxed italic">{evidence}</p>
      )}
    </div>
  )
}

function ObjectionCard({ objection, response }: { objection: string; response: string }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="border border-border rounded text-xs">
      <button
        type="button"
        onClick={() => setOpen(v => !v)}
        className="w-full text-left px-3 py-2.5 flex items-center gap-2 hover:bg-elevated transition-colors"
      >
        <span className="text-text-muted flex-shrink-0">
          {open ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
        </span>
        <span className="text-text-primary font-medium">{objection}</span>
      </button>
      {open && (
        <div className="px-3 pb-3 pl-8 text-text-secondary leading-relaxed border-t border-border pt-2">
          {response}
        </div>
      )}
    </div>
  )
}
