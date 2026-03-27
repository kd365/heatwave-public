import { useState } from 'react'
import type { RunStatus, PipelineResult } from '../api'

// Claude Sonnet 3.5 v2 blended rate — 80% input @ $3/MTok, 20% output @ $15/MTok
const COST_PER_TOKEN = (0.8 * 3 + 0.2 * 15) / 1_000_000

const STRATEGY_LABELS: Record<string, string> = {
  optimize_coverage:      'Coverage Maximization',
  optimize_response_time: 'Response Time',
  optimize_staged_reserve:'Staged Reserve',
}

interface Props {
  runStatus: RunStatus | null
  result?: PipelineResult | null
  recentRuns?: RunStatus[]
}

const AGENTS: {
  key: keyof Pick<RunStatus, 'agent_1_status' | 'agent_2_status' | 'agent_3_status'>
  label: string
  name: string
  desc: string
}[] = [
  {
    key: 'agent_1_status',
    label: 'A1',
    name: 'Spatial Triage',
    desc: 'Filters 911/311/weather/social · geocodes heat signals to H3 hex grid',
  },
  {
    key: 'agent_2_status',
    label: 'A2',
    name: 'Threat Assessment',
    desc: 'RAG-augmented hex scoring · surfaces NWS/OSHA doc conflicts',
  },
  {
    key: 'agent_3_status',
    label: 'A3',
    name: 'Dispatch Commander',
    desc: 'Autonomous strategy selection · assigns assets to critical zones',
  },
]

export function AgentPanel({ runStatus, result, recentRuns = [] }: Props) {
  const [collapsed, setCollapsed] = useState(true)
  const [obsCollapsed, setObsCollapsed] = useState(true)

  if (collapsed) {
    return (
      <aside className="agent-panel agent-panel--collapsed">
        <button
          className="agent-panel-toggle"
          onClick={() => setCollapsed(false)}
          title="Expand agent panel"
        >
          «
        </button>
        <span className="agent-panel-collapsed-label">AGENTS</span>
      </aside>
    )
  }

  return (
    <aside className="agent-panel">
      <div className="agent-panel-header">
        <span className="agent-panel-title">AGENT PIPELINE</span>
        <button
          className="agent-panel-toggle"
          onClick={() => setCollapsed(true)}
          title="Collapse agent panel"
        >
          »
        </button>
      </div>

      <div className="agent-panel-run-info">
        {runStatus
          ? <>Run <code>{runStatus.run_id.slice(-8)}</code> · <span className={`run-status-text run-status-text--${runStatus.status.toLowerCase()}`}>{runStatus.status}</span></>
          : 'No run yet — click ▶ Run Analysis'}
      </div>

      <div className="agent-panel-body">
        {AGENTS.map(agent => {
          const rawStatus = runStatus?.[agent.key] ?? 'IDLE'
          const status = (rawStatus as string).toUpperCase()
          return (
            <div
              key={agent.key}
              className={`agent-card agent-card--${status.toLowerCase()}`}
            >
              <div className="agent-card-top">
                <span className="agent-card-label">{agent.label}</span>
                <span className={`agent-status-badge agent-status-badge--${status.toLowerCase()}`}>
                  {status === 'RUNNING' && <span className="agent-spinner-dot" />}
                  {status}
                </span>
              </div>
              <div className="agent-card-name">{agent.name}</div>
              <div className="agent-card-desc">{agent.desc}</div>
              {status === 'RUNNING' && (
                <div className="agent-progress-bar">
                  <div className="agent-progress-fill" />
                </div>
              )}
            </div>
          )
        })}
      </div>

      <ObsSection
        runStatus={runStatus}
        result={result ?? null}
        recentRuns={recentRuns}
        collapsed={obsCollapsed}
        onToggle={() => setObsCollapsed(c => !c)}
      />
    </aside>
  )
}

function ObsSection({
  runStatus,
  result,
  recentRuns,
  collapsed,
  onToggle,
}: {
  runStatus: RunStatus | null
  result: PipelineResult | null
  recentRuns: RunStatus[]
  collapsed: boolean
  onToggle: () => void
}) {
  const dp = result?.dispatch_plan
  const strategy = dp?.strategy_used
  const summary = dp?.dispatch_plan?.summary
  const tokens = runStatus?.tokens_used ?? 0
  const duration_ms = runStatus?.duration_ms ?? null
  const estCost = tokens > 0 ? (tokens * COST_PER_TOKEN).toFixed(2) : null

  const completedRuns = recentRuns.filter(r => r.status === 'COMPLETE')
  const avgDurationMin = completedRuns.length > 0
    ? completedRuns.reduce((sum, r) => sum + (r.duration_ms ?? 0), 0) / completedRuns.length / 60_000
    : null

  return (
    <div className="obs-section">
      <div className="obs-header" onClick={onToggle}>
        <span className="obs-title">OBSERVABILITY</span>
        <span className="obs-toggle">{collapsed ? '▲' : '▼'}</span>
      </div>
      {!collapsed && (
        <div className="obs-body">
          {tokens === 0 && !strategy ? (
            <div className="obs-empty">No run data yet</div>
          ) : (
            <>
              {strategy && (
                <ObsRow label="Strategy" value={STRATEGY_LABELS[strategy] ?? strategy} highlight />
              )}
              {duration_ms != null && (
                <ObsRow label="Duration" value={`${(duration_ms / 60_000).toFixed(1)} min`} />
              )}
              {tokens > 0 && (
                <ObsRow label="Tokens" value={`${Math.round(tokens / 1000)}K`} />
              )}
              {estCost && (
                <ObsRow label="Est. cost" value={`~$${estCost}`} />
              )}
              {summary && (
                <ObsRow
                  label="Coverage"
                  value={`${summary.critical_covered}/${summary.critical_total} critical · ${summary.total_deployed} deployed`}
                />
              )}
              {completedRuns.length > 0 && (
                <div className="obs-divider" />
              )}
              {completedRuns.length > 0 && (
                <ObsRow
                  label="History"
                  value={`${completedRuns.length} run${completedRuns.length !== 1 ? 's' : ''}${avgDurationMin != null ? ` · avg ${avgDurationMin.toFixed(1)} min` : ''}`}
                />
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}

function ObsRow({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className="obs-row">
      <span className="obs-label">{label}</span>
      <span className={`obs-value${highlight ? ' obs-value--highlight' : ''}`}>{value}</span>
    </div>
  )
}
