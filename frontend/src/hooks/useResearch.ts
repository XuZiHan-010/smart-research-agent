import { useCallback, useMemo, useRef, useState } from 'react'
import {
  AppPhase,
  CitationRef,
  ClarificationQuestionnaire,
  ConfirmScopePayload,
  PipelineNodeId,
  PipelineStage,
  ResearchConfig,
  SSEEvent,
  THEME_LABELS,
  ThemeRunState,
  TodoState,
  ValidationSnapshot,
} from '../types'

const API = import.meta.env.VITE_API_URL ?? ''

const INITIAL_STAGES: PipelineStage[] = [
  { id: 'router', label: 'Router', status: 'idle' },
  { id: 'theme_orchestrator', label: 'Themes', status: 'idle' },
  { id: 'cross_validator', label: 'Validator', status: 'idle' },
  { id: 'compactor', label: 'Compact', status: 'idle' },
  { id: 'editor', label: 'Editor', status: 'idle' },
  { id: 'citation_resolver', label: 'Citations', status: 'idle' },
  { id: 'output_formatter', label: 'Output', status: 'idle' },
]

const cellToThemeStatus = (cellStatus?: string): ThemeRunState['status'] => {
  switch (cellStatus) {
    case 'success': return 'done'
    case 'partial': return 'researching'
    case 'error':   return 'failed'
    case 'empty':   return 'failed'
    case 'pending': return 'pending'
    default:        return 'pending'
  }
}

export function useResearch() {
  const [phase, setPhase] = useState<AppPhase>('idle')
  const [stages, setStages] = useState<PipelineStage[]>(INITIAL_STAGES)
  const [statusMessage, setStatusMsg] = useState('')
  const [todoState, setTodoState] = useState<TodoState>({})
  const [dimLabels, setDimLabels] = useState<Record<string, string>>({})
  const [streamedReport, setStreamed] = useState('')
  const [finalReport, setFinal] = useState('')
  const [currentJobId, setJobId] = useState<string | null>(null)
  const [errorMsg, setError] = useState('')
  const [logLines, setLogLines] = useState<string[]>([])
  const [pendingConfig, setPendingCfg] = useState<ResearchConfig | null>(null)
  const [questionnaire, setQuestionnaire] = useState<ClarificationQuestionnaire | null>(null)

  // ── Agentic loop state ────────────────────────────────────────────────────
  const [iteration, setIteration] = useState(1)
  const [themeStates, setThemeStates] = useState<Record<string, ThemeRunState>>({})
  const [validations, setValidations] = useState<ValidationSnapshot[]>([])
  const [citations, setCitations] = useState<Record<number, CitationRef>>({})
  const [retryArc, setRetryArc] = useState<{ id: number; themes: string[]; reason?: string } | null>(null)

  const esRef = useRef<EventSource | null>(null)
  const completedRef = useRef(false)
  const retryArcCounterRef = useRef(0)

  const addLog = useCallback((msg: string) => {
    setLogLines(prev => [...prev.slice(-99), msg])
  }, [])

  const resetStages = useCallback(() => {
    setStages(INITIAL_STAGES.map(s => ({ ...s, status: 'idle' as const, message: undefined })))
  }, [])

  const updateStage = useCallback((nodeId: string, patch: Partial<PipelineStage>) => {
    setStages(prev => prev.map(s => s.id === nodeId ? { ...s, ...patch } : s))
  }, [])

  // ── Derive ThemeRunState from todoState (fallback when backend doesn't emit theme_progress) ───
  const derivedThemeStates = useMemo<Record<string, ThemeRunState>>(() => {
    const dims = Object.keys(dimLabels).length > 0 ? Object.keys(dimLabels) : Object.keys(THEME_LABELS)
    const out: Record<string, ThemeRunState> = {}
    const companies = Object.keys(todoState)
    const group = companies[0] // single research domain

    dims.forEach(dim => {
      const overlay = themeStates[dim]
      const cell = group ? todoState[group]?.[dim] : undefined
      out[dim] = {
        theme_key: dim,
        label: dimLabels[dim] || THEME_LABELS[dim] || dim,
        status: overlay?.status ?? cellToThemeStatus(cell?.status),
        docs_found: overlay?.docs_found ?? cell?.docs_found ?? 0,
        quality_score: overlay?.quality_score,
        confidence: overlay?.confidence,
        retry_count: overlay?.retry_count ?? 0,
        citations_count: overlay?.citations_count ?? 0,
        gaps: overlay?.gaps,
        queries: overlay?.queries,
        sources: overlay?.sources,
      }
    })
    return out
  }, [todoState, dimLabels, themeStates])

  const attachSSE = useCallback((jobId: string) => {
    esRef.current?.close()
    completedRef.current = false
    const es = new EventSource(`${API}/api/research/${jobId}/stream`)
    esRef.current = es

    es.onmessage = (e: MessageEvent) => {
      const evt: SSEEvent = JSON.parse(e.data)

      if (evt.type === 'status') {
        const nodeId = evt.node as PipelineNodeId | undefined
        if (nodeId) {
          setStages(prev => prev.map(s => s.status === 'active' ? { ...s, status: 'done' } : s))
          updateStage(nodeId, { status: 'active', message: evt.message, iteration })
        }
        setStatusMsg(evt.message)
        addLog(`[${evt.node ?? '-'}] ${evt.message}`)
      }

      else if (evt.type === 'todo') {
        setTodoState(evt.todo_state)
        setDimLabels(evt.dim_labels)
      }

      else if (evt.type === 'stream') {
        setStreamed(prev => prev + evt.content)
      }

      else if (evt.type === 'theme_progress') {
        setThemeStates(prev => {
          const existing = prev[evt.theme_key]
          const next: ThemeRunState = {
            theme_key: evt.theme_key,
            label: evt.state.label ?? existing?.label ?? THEME_LABELS[evt.theme_key] ?? evt.theme_key,
            status: evt.state.status ?? existing?.status ?? 'pending',
            docs_found: evt.state.docs_found ?? existing?.docs_found ?? 0,
            quality_score: evt.state.quality_score ?? existing?.quality_score,
            confidence: evt.state.confidence ?? existing?.confidence,
            retry_count: evt.state.retry_count ?? existing?.retry_count ?? 0,
            citations_count: evt.state.citations_count ?? existing?.citations_count ?? 0,
            gaps: evt.state.gaps ?? existing?.gaps,
            queries: evt.state.queries ?? existing?.queries,
            sources: evt.state.sources ?? existing?.sources,
          }
          return { ...prev, [evt.theme_key]: next }
        })
      }

      else if (evt.type === 'validation') {
        setValidations(prev => [...prev, evt.snapshot])
        setIteration(evt.snapshot.iteration)
        addLog(`[validator] iter ${evt.snapshot.iteration} → ${evt.snapshot.decision} (score ${evt.snapshot.overall_score})`)
      }

      else if (evt.type === 'retry') {
        retryArcCounterRef.current += 1
        setRetryArc({ id: retryArcCounterRef.current, themes: evt.themes, reason: evt.reason })
        setIteration(evt.iteration)
        // mark stages as retrying
        updateStage('theme_orchestrator', { status: 'retrying', iteration: evt.iteration })
        // mark themes as retrying
        setThemeStates(prev => {
          const next = { ...prev }
          evt.themes.forEach(k => {
            const existing = next[k]
            next[k] = {
              theme_key: k,
              label: existing?.label ?? THEME_LABELS[k] ?? k,
              status: 'retrying',
              docs_found: existing?.docs_found ?? 0,
              retry_count: (existing?.retry_count ?? 0) + 1,
              citations_count: existing?.citations_count ?? 0,
              quality_score: existing?.quality_score,
              confidence: existing?.confidence,
              gaps: existing?.gaps,
              queries: existing?.queries,
              sources: existing?.sources,
            }
          })
          return next
        })
        addLog(`[retry] iter ${evt.iteration} → ${evt.themes.length} themes: ${evt.themes.join(', ')}`)
        // clear arc after 1.5s
        setTimeout(() => setRetryArc(null), 1500)
      }

      else if (evt.type === 'citation_resolved') {
        setCitations(prev => ({ ...prev, [evt.citation.index]: evt.citation }))
      }

      else if (evt.type === 'complete') {
        completedRef.current = true
        setStages(prev => prev.map(s => ({ ...s, status: 'done' as const })))
        setFinal(evt.report ?? '')
        setPhase('completed')
        setStatusMsg('Research complete')
        addLog('Pipeline complete.')
        es.close()
      }

      else if (evt.type === 'error') {
        setPhase('failed')
        setError(evt.message)
        setStatusMsg(evt.message)
        setStages(prev => prev.map(s => s.status === 'active' ? { ...s, status: 'error' as const } : s))
        addLog(`ERROR: ${evt.message}`)
        es.close()
      }
    }

    es.onerror = () => {
      if (!completedRef.current) {
        setPhase('failed')
        setError('Connection lost - please try again')
        setStatusMsg('Connection lost')
      }
      es.close()
    }
  }, [addLog, iteration, updateStage])

  const startClarification = useCallback(async (config: ResearchConfig) => {
    setPendingCfg(config)
    setPhase('clarifying')
    setError('')
    setQuestionnaire(null)
    setStreamed('')
    setFinal('')
    resetStages()
    try {
      const res = await fetch(`${API}/api/research/clarify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confirmed_domain: config.researchDomain }),
      })
      if (!res.ok) throw new Error('Failed to build questionnaire')
      const data = await res.json()
      setQuestionnaire(data)
      setPhase('confirming_scope')
    } catch (err) {
      setPhase('failed')
      setError(err instanceof Error ? err.message : 'Clarification failed')
    }
  }, [resetStages])

  const confirmScope = useCallback(async (payload: ConfirmScopePayload) => {
    setPhase('running')
    resetStages()
    setStreamed('')
    setFinal('')
    setTodoState({})
    setLogLines([])
    setError('')
    setIteration(1)
    setThemeStates({})
    setValidations([])
    setCitations({})
    setRetryArc(null)
    try {
      const res = await fetch(`${API}/api/research/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail ?? 'Failed to start research')
      }
      const data = await res.json()
      setJobId(data.job_id)
      attachSSE(data.job_id)
    } catch (err) {
      setPhase('failed')
      setError(err instanceof Error ? err.message : 'Failed to start research')
    }
  }, [attachSSE, resetStages])

  const reset = useCallback(() => {
    esRef.current?.close()
    setPhase('idle')
    resetStages()
    setStatusMsg('')
    setTodoState({})
    setDimLabels({})
    setStreamed('')
    setFinal('')
    setJobId(null)
    setError('')
    setLogLines([])
    setPendingCfg(null)
    setQuestionnaire(null)
    setIteration(1)
    setThemeStates({})
    setValidations([])
    setCitations({})
    setRetryArc(null)
  }, [resetStages])

  return {
    phase,
    stages,
    statusMessage,
    todoState,
    dimLabels,
    streamedReport,
    finalReport,
    currentJobId,
    errorMsg,
    logLines,
    pendingConfig,
    questionnaire,
    // agentic loop
    iteration,
    themeStates: derivedThemeStates,
    validations,
    citations,
    retryArc,
    // actions
    startClarification,
    confirmScope,
    reset,
  }
}
