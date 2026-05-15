import { useState } from 'react'
import { AnimatePresence } from 'framer-motion'
import { History, Workflow } from 'lucide-react'

import { Sidebar } from './components/Sidebar'
import { OrbitTracker } from './components/OrbitTracker'
import { ReportViewer } from './components/ReportViewer'
import { HistoryDrawer } from './components/HistoryDrawer'
import { EmptyState } from './components/EmptyState'
import { LandscapePrompt } from './components/LandscapePrompt'
import { ClarificationPanel } from './components/ClarificationPanel'
import { TracesDrawer } from './components/TracesDrawer'
import { useResearch } from './hooks/useResearch'
import { ResearchConfig } from './types'

export default function App() {
  const [historyOpen, setHistoryOpen] = useState(false)
  const [tracesOpen, setTracesOpen] = useState(false)
  const [historyReport, setHistoryReport] = useState<{ jobId: string; report: string } | null>(null)

  const {
    phase,
    stages,
    statusMessage,
    streamedReport,
    finalReport,
    currentJobId,
    errorMsg,
    logLines,
    pendingConfig,
    questionnaire,
    iteration,
    themeStates,
    validations,
    citations,
    retryArc,
    startClarification,
    confirmScope,
    reset,
  } = useResearch()

  const report = finalReport || streamedReport
  const isRunning = phase === 'clarifying' || phase === 'confirming_scope' || phase === 'running'
  const displayReport = historyReport ? historyReport.report : report
  const displayJobId = historyReport ? historyReport.jobId : currentJobId
  const isHistoryView = !!historyReport

  const handleStart = (config: ResearchConfig) => {
    setHistoryReport(null)
    startClarification(config)
  }

  const handleHistoryLoad = (jobId: string, loadedReport: string) => {
    setHistoryReport({ jobId, report: loadedReport })
    setHistoryOpen(false)
  }

  const clearHistory = () => {
    setHistoryReport(null)
    reset()
  }

  const statusDot =
    isRunning ? 'bg-accent animate-pulse' :
    phase === 'completed' ? 'bg-active-green' :
    phase === 'failed' ? 'bg-error-red' : 'bg-border-bright'

  const statusLabel =
    isRunning ? 'Active' :
    phase === 'completed' ? 'Complete' :
    phase === 'failed' ? 'Error' : 'Ready'

  const showSidebar = !(phase === 'idle' && !isHistoryView)

  return (
    <div className="flex h-screen overflow-hidden">
      <LandscapePrompt />
      {showSidebar && (
        <Sidebar
          onStart={handleStart}
          onReset={isHistoryView ? clearHistory : reset}
          isRunning={isRunning}
        />
      )}

      <main className="flex-1 flex flex-col overflow-hidden">
        <header className="flex items-center justify-between px-8 py-3.5 border-b border-border flex-shrink-0">
          <div className="flex items-center gap-3">
            <span className="font-display text-lg font-light tracking-wide text-text-primary">
              Market Study Agent
            </span>
            <span className="font-mono text-[10px] text-text-muted px-1.5 py-0.5 border border-border rounded">
              v4.0
            </span>
            {isHistoryView && (
              <span className="font-mono text-[10px] text-accent px-1.5 py-0.5 border border-accent/30 bg-accent/5 rounded">
                History View
              </span>
            )}
          </div>

          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5">
              <span className={`w-1.5 h-1.5 rounded-full ${statusDot}`} />
              <span className="font-mono text-[10px] text-text-muted uppercase tracking-widest">
                {statusLabel}
              </span>
            </div>
            <div className="w-px h-4 bg-border" />
            <button
              onClick={() => setTracesOpen(true)}
              disabled={!displayJobId}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded border border-border text-text-secondary text-xs font-mono hover:border-border-bright hover:text-text-primary disabled:opacity-30 transition-colors"
            >
              <Workflow size={12} />
              Agent Decisions
            </button>
            <button
              onClick={() => setHistoryOpen(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded border border-border text-text-secondary text-xs font-mono hover:border-border-bright hover:text-text-primary transition-colors"
            >
              <History size={12} />
              History
            </button>
          </div>
        </header>

        <div className="flex-1 overflow-hidden p-8">
          {phase === 'idle' && !isHistoryView && (
            <EmptyState onStart={handleStart} onLoadHistory={handleHistoryLoad} />
          )}

          {phase === 'running' && (
            <div className={`h-full overflow-hidden ${report ? 'grid grid-cols-5 gap-8' : 'flex'}`}>
              <div className={`${report ? 'col-span-2' : 'flex-1'} overflow-y-auto pr-2`}>
                <OrbitTracker
                  stages={stages}
                  statusMessage={statusMessage}
                  iteration={iteration}
                  themeStates={themeStates}
                  validations={validations}
                  retryArc={retryArc}
                  logLines={logLines}
                  researchDomain={pendingConfig?.researchDomain}
                />
              </div>
              {report && (
                <div className="col-span-3 overflow-y-auto">
                  <ReportViewer report={report} jobId={currentJobId} isStreaming citations={citations} />
                </div>
              )}
            </div>
          )}

          {(phase === 'completed' || isHistoryView) && displayReport && (
            <div className="h-full overflow-y-auto">
              <ReportViewer report={displayReport} jobId={displayJobId} isStreaming={false} citations={citations} />
            </div>
          )}

          {phase === 'failed' && (
            <div className="flex flex-col items-center justify-center h-full gap-4">
              <span className="text-4xl">!</span>
              <p className="font-mono text-error-red text-sm max-w-md text-center">{errorMsg}</p>
              <button
                onClick={reset}
                className="px-4 py-2 border border-border rounded text-xs font-mono text-text-secondary hover:border-border-bright hover:text-text-primary transition-colors"
              >
                Try Again
              </button>
            </div>
          )}
        </div>
      </main>

      <AnimatePresence>
        {phase === 'confirming_scope' && questionnaire && pendingConfig && (
          <ClarificationPanel
            questionnaire={questionnaire}
            config={pendingConfig}
            onConfirm={confirmScope}
            onCancel={reset}
          />
        )}
      </AnimatePresence>

      <HistoryDrawer open={historyOpen} onClose={() => setHistoryOpen(false)} onLoad={handleHistoryLoad} />
      <TracesDrawer open={tracesOpen} jobId={displayJobId} onClose={() => setTracesOpen(false)} />
    </div>
  )
}
