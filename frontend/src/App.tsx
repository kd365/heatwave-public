import { useState, useEffect, useMemo } from 'react'
import { gridDisk, latLngToCell } from 'h3-js'
import { useQuery } from '@tanstack/react-query'
import 'leaflet/dist/leaflet.css'
import { MapContainer, TileLayer } from 'react-leaflet'
import { HexLayer } from './components/HexLayer'
import { Legend } from './components/Legend'
import { AssetLayer } from './components/AssetLayer'
import { AgentPanel } from './components/AgentPanel'
import { OrdersPanel } from './components/OrdersPanel'
import { triggerAnalysis, fetchRunStatus, fetchResult, fetchLatestRun, fetchAssets, fetchRuns } from './api'
import type { HexEvent, RunStatus, PipelineResult, DispatchOrder, Asset, ThreatScore } from './api'
import './App.css'

const DALLAS_CENTER: [number, number] = [32.7767, -96.797]
const DEFAULT_ZOOM = 11

function App() {
  const [activeRunId, setActiveRunId] = useState<string | null>(null)
  const [isTriggering, setIsTriggering] = useState(false)
  const [targetDate, setTargetDate] = useState('2023-08-18')

  // Available dates with temperature context
  const DATES = [
    { date: '2023-08-04', temp: 104.4, label: 'Aug 4 — 104°F' },
    { date: '2023-08-05', temp: 105.5, label: 'Aug 5 — 106°F' },
    { date: '2023-08-06', temp: 103.9, label: 'Aug 6 — 104°F' },
    { date: '2023-08-07', temp: 103.0, label: 'Aug 7 — 103°F' },
    { date: '2023-08-08', temp: 101.4, label: 'Aug 8 — 101°F' },
    { date: '2023-08-09', temp: 106.6, label: 'Aug 9 — 107°F 🔴' },
    { date: '2023-08-10', temp: 107.7, label: 'Aug 10 — 108°F 🔴' },
    { date: '2023-08-11', temp: 107.3, label: 'Aug 11 — 107°F 🔴' },
    { date: '2023-08-12', temp: 107.7, label: 'Aug 12 — 108°F 🔴' },
    { date: '2023-08-13', temp: 106.7, label: 'Aug 13 — 107°F 🔴' },
    { date: '2023-08-14', temp: 101.6, label: 'Aug 14 — 102°F' },
    { date: '2023-08-15', temp: 95.9, label: 'Aug 15 — 96°F 🟢' },
    { date: '2023-08-16', temp: 94.2, label: 'Aug 16 — 94°F 🟢 (coolest)' },
    { date: '2023-08-17', temp: 108.5, label: 'Aug 17 — 109°F 🔴🔴' },
    { date: '2023-08-18', temp: 109.3, label: 'Aug 18 — 109°F 🔴🔴 (peak)' },
    { date: '2023-08-19', temp: 106.5, label: 'Aug 19 — 107°F 🔴' },
    { date: '2023-08-20', temp: 107.2, label: 'Aug 20 — 107°F 🔴' },
    { date: '2023-08-21', temp: 104.4, label: 'Aug 21 — 104°F' },
    { date: '2023-08-22', temp: 104.1, label: 'Aug 22 — 104°F' },
    { date: '2023-08-23', temp: 103.6, label: 'Aug 23 — 104°F' },
    { date: '2023-08-24', temp: 105.9, label: 'Aug 24 — 106°F' },
    { date: '2023-08-25', temp: 107.6, label: 'Aug 25 — 108°F 🔴' },
    { date: '2023-08-26', temp: 107.3, label: 'Aug 26 — 107°F 🔴' },
    { date: '2023-08-27', temp: 99.1, label: 'Aug 27 — 99°F 🟢' },
  ]

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
  const { data: result } = useQuery<PipelineResult>({
    queryKey: ['result', activeRunId],
    queryFn: () => fetchResult(activeRunId!),
    enabled: !!activeRunId && runStatus?.status === 'COMPLETE',
  })

  // Fetch all recent runs for observability history
  const { data: recentRuns = [] } = useQuery({
    queryKey: ['runs'],
    queryFn: fetchRuns,
    staleTime: 30_000,
  })

  const hexEvents: HexEvent[] = useMemo(
    () => result?.hex_events?.hex_events ?? [],
    [result]
  )
  const orders: DispatchOrder[] = (() => {
    const dp = result?.dispatch_plan
    if (!dp) return []
    // Check all possible paths where orders might be
    if (dp.orders?.length) return dp.orders
    if (dp.dispatch_plan?.orders?.length) return dp.dispatch_plan.orders
    return []
  })()
  const status = runStatus?.status ?? latestRun?.status ?? 'IDLE'

  // Load asset inventory (cooling centers + mobile fleet)
  const { data: assets = [] } = useQuery({
    queryKey: ['assets'],
    queryFn: fetchAssets,
    staleTime: Infinity,
  })

  const activatedCoolingIds: string[] = useMemo(() => {
    const fromResult: string[] = result?.dispatch_plan?.cooling_centers_activated ?? []
    // Validate LLM IDs against real asset inventory — LLM sometimes invents IDs
    // that don't match the actual COOL-XXX format used in the inventory
    const knownIds = new Set(assets.map(a => a.id))
    const validFromResult = fromResult.filter(id => knownIds.has(id))
    if (validFromResult.length > 0) return validFromResult
    // Frontend geometry fallback: activate cooling centers near HIGH/CRITICAL hex events
    if (!assets.length || !hexEvents.length) return []
    const ACTIVATION_RADIUS = 2
    const HIGH_SEVERITY_THRESHOLD = 0.65
    const activationZone = new Set<string>()
    for (const h of hexEvents) {
      const threatScore = (result?.threat_map?.threat_map ?? []).find((t: ThreatScore) => t.hex_id === h.hex_id)
      if ((threatScore?.risk_score ?? 0) >= HIGH_SEVERITY_THRESHOLD) {
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
          const ccHex = latLngToCell(a.home_lat, a.home_lon, 7)
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
      const { run_id } = await triggerAnalysis(targetDate)
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
          <select
            className="date-selector"
            value={targetDate}
            onChange={(e) => setTargetDate(e.target.value)}
            disabled={isTriggering || status === 'RUNNING'}
          >
            {DATES.map(d => (
              <option key={d.date} value={d.date}>{d.label}</option>
            ))}
          </select>
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
        <div className="app-map-row">
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
            {hexEvents.length > 0 && <HexLayer hexEvents={hexEvents} threatMap={result?.threat_map?.threat_map ?? []} />}
            <AssetLayer
              assets={assets}
              orders={orders}
              activatedCoolingIds={activatedCoolingIds}
            />
          </MapContainer>

          <AgentPanel
            runStatus={runStatus ?? latestRun ?? null}
            result={result ?? null}
            recentRuns={recentRuns}
          />
          <Legend hexEvents={hexEvents} threatMap={result?.threat_map?.threat_map ?? []} runStatus={runStatus ?? latestRun ?? null} />
        </div>

        <OrdersPanel orders={orders} assets={assets} />
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
