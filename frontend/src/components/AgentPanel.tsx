import { useState } from 'react'
import type { RunStatus } from '../api'

interface Props {
  runStatus: RunStatus | null
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

export function AgentPanel({ runStatus }: Props) {
  const [collapsed, setCollapsed] = useState(false)

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
    </aside>
  )
}
