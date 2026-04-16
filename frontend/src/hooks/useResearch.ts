import { useState, useCallback, useRef } from 'react'
import {
  AppPhase, ResearchConfig, CompanyInput, DiscoverySuggestion,
  PipelineStage, PipelineNodeId, TodoState, BattlecardData, SSEEvent,
} from '../types'

const API = import.meta.env.VITE_API_URL ?? ''

// ── Pipeline stage definitions ────────────────────────────────────────────────

const INITIAL_STAGES: PipelineStage[] = [
  { id: 'router',              label: 'Router',       status: 'idle' },
  { id: 'grounding',           label: 'Grounding',    status: 'idle' },
  { id: 'research_dispatcher', label: 'Research',     status: 'idle' },
  { id: 'collector',           label: 'Collector',    status: 'idle' },
  { id: 'curator',             label: 'Curator',      status: 'idle' },
  { id: 'evaluator',           label: 'Evaluator',    status: 'idle' },
  { id: 'comparator',          label: 'Comparator',   status: 'idle' },
  { id: 'battlecard_builder',  label: 'Battlecard',   status: 'idle' },
  { id: 'editor',              label: 'Editor',       status: 'idle' },
  { id: 'output_formatter',    label: 'Formatter',    status: 'idle' },
]

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useResearch() {
  const [phase,          setPhase]     = useState<AppPhase>('idle')
  const [stages,         setStages]    = useState<PipelineStage[]>(INITIAL_STAGES)
  const [statusMessage,  setStatusMsg] = useState('')
  const [todoState,      setTodoState] = useState<TodoState>({})
  const [dimLabels,      setDimLabels] = useState<Record<string, string>>({})
  const [streamedReport, setStreamed]  = useState('')
  const [finalReport,    setFinal]     = useState('')
  const [battlecard,     setBattlecard]= useState<BattlecardData | null>(null)
  const [currentJobId,   setJobId]     = useState<string | null>(null)
  const [errorMsg,       setError]     = useState('')

  // Discovery phase
  const [suggestions, setSuggestions] = useState<DiscoverySuggestion[]>([])
  const [pendingConfig, setPendingCfg] = useState<ResearchConfig | null>(null)

  // Log messages for the terminal panel
  const [logLines, setLogLines] = useState<string[]>([])

  const esRef        = useRef<EventSource | null>(null)
  const completedRef = useRef(false)   // tracks SSE success; used in onerror to avoid false failure

  // ── Helpers ─────────────────────────────────────────────────────────────────

  const addLog = useCallback((msg: string) => {
    setLogLines(prev => [...prev.slice(-99), msg])
  }, [])

  const updateStage = useCallback((nodeId: string, patch: Partial<PipelineStage>) => {
    setStages(prev => prev.map(s => s.id === nodeId ? { ...s, ...patch } : s))
  }, [])

  const resetStages = useCallback(() => {
    setStages(INITIAL_STAGES.map(s => ({ ...s, status: 'idle' as const, message: undefined })))
  }, [])

  // ── SSE listener ─────────────────────────────────────────────────────────────

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
          // Mark previously active stage as done
          setStages(prev => prev.map(s =>
            s.status === 'active' ? { ...s, status: 'done' } : s
          ))
          updateStage(nodeId, { status: 'active', message: evt.message })
        }
        setStatusMsg(evt.message)
        addLog(`[${evt.node ?? '—'}] ${evt.message}`)
      }

      if (evt.type === 'todo') {
        setTodoState(evt.todo_state)
        setDimLabels(evt.dim_labels)
      }

      if (evt.type === 'stream') {
        setStreamed(prev => prev + evt.content)
      }

      if (evt.type === 'complete') {
        completedRef.current = true
        setStages(prev => prev.map(s => ({ ...s, status: 'done' as const })))
        setFinal(evt.report ?? '')
        setPhase('completed')
        setStatusMsg('Research complete')
        addLog('Pipeline complete.')
        es.close()

        // Fetch battlecard separately
        if (jobId) {
          fetch(`${API}/api/research/${jobId}/battlecard`)
            .then(r => r.ok ? r.json() : null)
            .then(d => { if (d?.battlecard) setBattlecard(d.battlecard) })
            .catch(() => {})
        }
      }

      if (evt.type === 'error') {
        setPhase('failed')
        setError(evt.message)
        setStatusMsg(evt.message)
        setStages(prev => prev.map(s =>
          s.status === 'active' ? { ...s, status: 'error' as const } : s
        ))
        addLog(`ERROR: ${evt.message}`)
        es.close()
      }
    }

    es.onerror = () => {
      // completedRef avoids false failure when es.close() triggers onerror after success
      if (!completedRef.current) {
        setPhase('failed')
        setError('Connection lost — please try again')
        setStatusMsg('Connection lost')
      }
      es.close()
    }
  }, [addLog, updateStage])

  // ── Public actions ───────────────────────────────────────────────────────────

  /** Step 1a: user clicks "Auto-Discover" */
  const discoverCompetitors = useCallback(async (config: ResearchConfig) => {
    setPendingCfg(config)
    setPhase('discovering')
    setError('')
    try {
      const res = await fetch(`${API}/api/research/discover`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target_company: config.target_company,
          target_website: config.target_website,
          competitors:    config.competitorNames,
        }),
      })
      const data = await res.json()
      setSuggestions(data.suggestions ?? [])
      setPhase('confirming')
    } catch {
      setError('Discovery failed — check your connection')
      setPhase('idle')
    }
  }, [])

  /** Step 1b: user confirms discovered + manual competitors, or skips discovery */
  const startWithCompanies = useCallback(async (
    config:       ResearchConfig,
    allCompanies: CompanyInput[],
  ) => {
    setPhase('running')
    resetStages()
    setStreamed('')
    setFinal('')
    setBattlecard(null)
    setTodoState({})
    setLogLines([])
    setError('')

    try {
      const res = await fetch(`${API}/api/research/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target_company: config.target_company,
          target_website: config.target_website,
          all_companies:  allCompanies,
          report_type:    config.report_type,
          depth:          config.depth,
          output_format:  config.output_format,
          language:       config.language,
          template:       config.template,
        }),
      })
      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail ?? 'Failed to start research')
      }
      const data = await res.json()
      const jobId: string = data.job_id
      setJobId(jobId)
      attachSSE(jobId)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to start research'
      setPhase('failed')
      setError(msg)
    }
  }, [resetStages, attachSSE])

  /** Edit an existing report */
  const editReport = useCallback(async (
    jobId:       string,
    mode:        'quick_edit' | 'targeted_refresh' | 'full_refresh',
    instruction: string,
  ) => {
    setPhase('running')
    resetStages()
    setStreamed('')
    setLogLines([])
    setError('')

    try {
      const res = await fetch(`${API}/api/research/${jobId}/edit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ edit_mode: mode, edit_instruction: instruction }),
      })
      if (!res.ok) throw new Error('Edit request failed')
      attachSSE(jobId)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Edit failed'
      setPhase('failed')
      setError(msg)
    }
  }, [resetStages, attachSSE])

  /** Reset everything back to idle */
  const reset = useCallback(() => {
    esRef.current?.close()
    setPhase('idle')
    resetStages()
    setStatusMsg('')
    setTodoState({})
    setDimLabels({})
    setStreamed('')
    setFinal('')
    setBattlecard(null)
    setJobId(null)
    setError('')
    setSuggestions([])
    setPendingCfg(null)
    setLogLines([])
  }, [resetStages])

  return {
    // state
    phase,
    stages,
    statusMessage,
    todoState,
    dimLabels,
    streamedReport,
    finalReport,
    battlecard,
    currentJobId,
    errorMsg,
    logLines,
    // discovery
    suggestions,
    pendingConfig,
    // actions
    discoverCompetitors,
    startWithCompanies,
    editReport,
    reset,
  }
}
