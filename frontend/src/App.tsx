import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import 'leaflet/dist/leaflet.css'
import { MapContainer, TileLayer } from 'react-leaflet'
import { HexLayer } from './components/HexLayer'
import { Legend } from './components/Legend'
import { triggerAnalysis, fetchRunStatus, fetchResult, fetchLatestRun } from './api'
import type { HexEvent, RunStatus } from './api'
import './App.css'

const DALLAS_CENTER: [number, number] = [32.7767, -96.797]
const DEFAULT_ZOOM = 11

function App() {
  const [activeRunId, setActiveRunId] = useState<string | null>(null)
  const [isTriggering, setIsTriggering] = useState(false)

  // On load, pick up the latest completed run
  const { data: latestRun } = useQuery({
    queryKey: ['latestRun'],
    queryFn: fetchLatestRun,
  })

  useEffect(() => {
    if (latestRun?.run_id && !activeRunId) {
      setActiveRunId(latestRun.run_id)
    }
  }, [latestRun, activeRunId])

  // Poll active run status while RUNNING
  const { data: runStatus } = useQuery<RunStatus>({
    queryKey: ['runStatus', activeRunId],
    queryFn: () => fetchRunStatus(activeRunId!),
    enabled: !!activeRunId,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'RUNNING' ? 5000 : false
    },
  })

  // Fetch result when COMPLETE
  const { data: result } = useQuery({
    queryKey: ['result', activeRunId],
    queryFn: () => fetchResult(activeRunId!),
    enabled: !!activeRunId && runStatus?.status === 'COMPLETE',
  })

  const hexEvents: HexEvent[] = result?.hex_events?.hex_events ?? []
  const status = runStatus?.status ?? latestRun?.status ?? 'IDLE'

  async function handleRunAnalysis() {
    setIsTriggering(true)
    try {
      const { run_id } = await triggerAnalysis()
      setActiveRunId(run_id)
    } finally {
      setIsTriggering(false)
    }
  }

  return (
    <div className="app-layout">
      <header className="app-header">
        <h1>🌡️ HEATWAVE</h1>
        <span className="app-subtitle">Dallas Heat Emergency Response — Aug 2023</span>
        <div className="header-right">
          <AgentStatusBadges runStatus={runStatus ?? null} />
          <button
            className={`run-btn ${isTriggering || status === 'RUNNING' ? 'running' : ''}`}
            onClick={handleRunAnalysis}
            disabled={isTriggering || status === 'RUNNING'}
          >
            {isTriggering ? 'Starting…' : status === 'RUNNING' ? 'Running…' : '▶ Run Analysis'}
          </button>
        </div>
      </header>

      <main className="app-main">
        <MapContainer
          center={DALLAS_CENTER}
          zoom={DEFAULT_ZOOM}
          className="map-container"
          zoomControl={true}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          {hexEvents.length > 0 && <HexLayer hexEvents={hexEvents} />}
        </MapContainer>

        <Legend hexEvents={hexEvents} runStatus={runStatus ?? latestRun ?? null} />
      </main>
    </div>
  )
}

function AgentStatusBadges({ runStatus }: { runStatus: RunStatus | null }) {
  if (!runStatus) return null
  const agents = [
    { label: 'A1', status: runStatus.agent_1_status },
    { label: 'A2', status: runStatus.agent_2_status },
    { label: 'A3', status: runStatus.agent_3_status },
  ]
  return (
    <div className="agent-badges">
      {agents.map(({ label, status }) => (
        <span key={label} className={`badge badge-${(status ?? 'IDLE').toLowerCase()}`}>
          {label}: {status ?? 'IDLE'}
        </span>
      ))}
    </div>
  )
}

export default App
