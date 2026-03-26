import { useState, useEffect, useMemo } from 'react'
import { gridDisk, latLngToCell } from 'h3-js'
import { useQuery } from '@tanstack/react-query'
import 'leaflet/dist/leaflet.css'
import { MapContainer, TileLayer } from 'react-leaflet'
import { HexLayer } from './components/HexLayer'
import { Legend } from './components/Legend'
import { AssetLayer } from './components/AssetLayer'
import { triggerAnalysis, fetchRunStatus, fetchResult, fetchLatestRun, fetchAssets } from './api'
import type { HexEvent, RunStatus, DispatchOrder, Asset } from './api'
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
  const orders: DispatchOrder[] = result?.dispatch_plan?.dispatch_plan?.orders ?? []
  const status = runStatus?.status ?? latestRun?.status ?? 'IDLE'

  // Load asset inventory (cooling centers + mobile fleet)
  const { data: assets = [] } = useQuery({
    queryKey: ['assets'],
    queryFn: fetchAssets,
    staleTime: Infinity,
  })

  const activatedCoolingIds: string[] = useMemo(() => {
    const fromResult: string[] = result?.dispatch_plan?.cooling_centers_activated ?? []
    if (fromResult.length > 0) return fromResult
    // Frontend geometry fallback: activate cooling centers near HIGH/CRITICAL hex events
    if (!assets.length || !hexEvents.length) return []
    const ACTIVATION_RADIUS = 2
    const HIGH_SEVERITY_THRESHOLD = 0.65
    const activationZone = new Set<string>()
    for (const h of hexEvents) {
      if ((h.severity_score ?? 0) >= HIGH_SEVERITY_THRESHOLD) {
        for (const ring of gridDisk(h.hex_id, ACTIVATION_RADIUS)) {
          activationZone.add(ring)
        }
      }
    }
    if (activationZone.size === 0) return []
    return (assets as Asset[])
      .filter(a => a.asset_type.startsWith('cooling_center'))
      .filter(a => {
        if (a.home_lat == null || a.home_lon == null) return false
        try {
          const ccHex = latLngToCell(a.home_lat, a.home_lon, 8)
          return activationZone.has(ccHex)
        } catch {
          return false
        }
      })
      .map(a => a.id)
  }, [result, assets, hexEvents])

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
          <AssetLayer
            assets={assets}
            orders={orders}
            activatedCoolingIds={activatedCoolingIds}
          />
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
