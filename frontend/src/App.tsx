import { useState } from 'react'
import { AnimatePresence } from 'framer-motion'
import { History } from 'lucide-react'

import { Sidebar }          from './components/Sidebar'
import { DiscoveryPanel }   from './components/DiscoveryPanel'
import { ProgressTracker }  from './components/ProgressTracker'
import { ReportViewer }     from './components/ReportViewer'
import { HistoryDrawer }    from './components/HistoryDrawer'
import { EmptyState }       from './components/EmptyState'
import { useResearch }      from './hooks/useResearch'

import { ResearchConfig, CompanyInput } from './types'

export default function App() {
  const [historyOpen, setHistoryOpen] = useState(false)

  const {
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
  } = useResearch()

  const report    = finalReport || streamedReport
  const isRunning = phase === 'running' || phase === 'discovering'

  // ── Handlers ────────────────────────────────────────────────────────────────

  const handleStart = (config: ResearchConfig) => {
    // Build all_companies with target first, then user-entered competitors
    const companies: CompanyInput[] = [
      { name: config.target_company, website: config.target_website, source: 'target' },
      ...config.competitorNames.map(n => ({ name: n, website: '', source: 'user' as const })),
    ]
    startWithCompanies(config, companies)
  }

  const handleDiscover = (config: ResearchConfig) => {
    discoverCompetitors(config)
  }

  const handleConfirm = (config: ResearchConfig, companies: CompanyInput[]) => {
    startWithCompanies(config, companies)
  }

  const handleHistoryLoad = (_jobId: string, historyReport: string) => {
    // Hydrate report from history — sets finalReport via a simple mechanism:
    // We don't have a setState hook for this here; instead we reload the page
    // with the report already fetched. For simplicity, open the report in
    // the viewer via a query param approach — or just show an alert and let
    // the user know. In a production build, hook into the useResearch state.
    // For now, the HistoryDrawer will call onLoad which can be wired to
    // a local state here.
    setHistoryReport({ jobId: _jobId, report: historyReport })
    setHistoryOpen(false)
  }

  // Local state for history-loaded report (separate from live pipeline)
  const [historyReport, setHistoryReport] = useState<{ jobId: string; report: string } | null>(null)

  // If history report loaded, show it in the viewer
  const displayReport   = historyReport ? historyReport.report   : report
  const displayJobId    = historyReport ? historyReport.jobId     : currentJobId
  const isHistoryView   = !!historyReport
  const clearHistory    = () => { setHistoryReport(null); reset() }

  // ── Status indicator ────────────────────────────────────────────────────────

  const statusDot =
    isRunning    ? 'bg-accent animate-pulse' :
    phase === 'completed' ? 'bg-active-green' :
    phase === 'failed'    ? 'bg-error-red' : 'bg-border-bright'

  const statusLabel =
    isRunning    ? 'Active' :
    phase === 'completed' ? 'Complete' :
    phase === 'failed'    ? 'Error' : 'Ready'

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar — config form */}
      <Sidebar
        onStart={handleStart}
        onDiscover={handleDiscover}
        onReset={isHistoryView ? clearHistory : reset}
        isRunning={isRunning}
      />

      {/* Main content */}
      <main className="flex-1 flex flex-col overflow-hidden">
        {/* Topbar */}
        <header className="flex items-center justify-between px-8 py-3.5 border-b border-border flex-shrink-0">
          <div className="flex items-center gap-3">
            <span className="font-display text-lg font-light tracking-wide text-text-primary">
              Competitor Research
            </span>
            <span className="font-mono text-[10px] text-text-muted px-1.5 py-0.5 border border-border rounded">
              v3.0
            </span>
            {isHistoryView && (
              <span className="font-mono text-[10px] text-accent px-1.5 py-0.5 border border-accent/30
                               bg-accent/5 rounded">
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
              onClick={() => setHistoryOpen(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded border border-border
                         text-text-secondary text-xs font-mono
                         hover:border-border-bright hover:text-text-primary transition-colors"
            >
              <History size={12} />
              History
            </button>
          </div>
        </header>

        {/* Content area */}
        <div className="flex-1 overflow-hidden p-8">

          {/* Idle / empty */}
          {phase === 'idle' && !isHistoryView && <EmptyState />}

          {/* Discovering spinner */}
          {phase === 'discovering' && (
            <div className="flex items-center justify-center h-full">
              <div className="text-center space-y-3">
                <div className="w-8 h-8 border-2 border-accent border-t-transparent rounded-full
                                animate-spin mx-auto" />
                <p className="font-mono text-sm text-text-secondary">
                  Searching for competitors…
                </p>
              </div>
            </div>
          )}

          {/* Running — split view */}
          {phase === 'running' && (
            <div className={`h-full overflow-hidden ${report ? 'grid grid-cols-5 gap-8' : 'flex'}`}>
              {/* Progress column */}
              <div className={`${report ? 'col-span-2' : 'flex-1'} overflow-y-auto`}>
                <ProgressTracker
                  stages={stages}
                  statusMessage={statusMessage}
                  todoState={todoState}
                  dimLabels={dimLabels}
                  logLines={logLines}
                />
              </div>
              {/* Streaming report column */}
              {report && (
                <div className="col-span-3 overflow-y-auto">
                  <ReportViewer
                    report={report}
                    jobId={currentJobId}
                    isStreaming={true}
                    battlecard={battlecard}
                  />
                </div>
              )}
            </div>
          )}

          {/* Completed */}
          {(phase === 'completed' || isHistoryView) && displayReport && (
            <div className="h-full overflow-y-auto">
              <ReportViewer
                report={displayReport}
                jobId={displayJobId}
                isStreaming={false}
                battlecard={battlecard}
                onEdit={!isHistoryView && currentJobId
                  ? (mode, instruction) => editReport(currentJobId, mode, instruction)
                  : undefined
                }
              />
            </div>
          )}

          {/* Failed */}
          {phase === 'failed' && (
            <div className="flex flex-col items-center justify-center h-full gap-4">
              <span className="text-4xl">⚠</span>
              <p className="font-mono text-error-red text-sm max-w-md text-center">{errorMsg}</p>
              <button
                onClick={reset}
                className="px-4 py-2 border border-border rounded text-xs font-mono
                           text-text-secondary hover:border-border-bright hover:text-text-primary
                           transition-colors"
              >
                Try Again
              </button>
            </div>
          )}
        </div>
      </main>

      {/* Discovery confirmation modal */}
      <AnimatePresence>
        {phase === 'confirming' && pendingConfig && (
          <DiscoveryPanel
            config={pendingConfig}
            suggestions={suggestions}
            isLoading={false}
            onConfirm={handleConfirm}
            onCancel={reset}
          />
        )}
      </AnimatePresence>

      {/* History drawer */}
      <HistoryDrawer
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        onLoad={handleHistoryLoad}
      />
    </div>
  )
}
