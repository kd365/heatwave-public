const API_BASE = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '')
  ?? 'https://b5wnyxsvm4.execute-api.us-east-1.amazonaws.com'

export interface Asset {
  id: string
  asset_type: string
  description: string
  home_address: string
  home_zip: string
  home_lat: number
  home_lon: number
  status: string
  shift: string
  capacity: number
  coverage_radius: number
}

export interface DispatchOrder {
  asset_id: string
  from_hex: string
  to_hex: string
  distance: number
  role: string
}

export interface HexEvent {
  hex_id: string
  event_type: string
  severity_score: number
  source_count: number
  sources: string[]
  weather_count: number
  weather_max_temp: number
  dispatch_count: number
  service_count: number
  social_count: number
}

export interface RunStatus {
  run_id: string
  status: 'RUNNING' | 'COMPLETE' | 'ERROR' | 'IDLE'
  agent_1_status: string
  agent_2_status: string
  agent_3_status: string
  tokens_used: number
  duration_ms: number | null
  error_message: string | null
  created_at: string
}

export interface PipelineResult extends RunStatus {
  hex_events: { hex_events: HexEvent[] }
  threat_map: unknown
  dispatch_plan: {
    strategy_used: string
    strategy_justification: string
    dispatch_plan: {
      orders: DispatchOrder[]
      summary: {
        total_deployed: number
        total_staged: number
        critical_covered: number
        critical_total: number
      }
    }
    cooling_centers_activated: string[]
    recommendations: string
  }
}

export async function triggerAnalysis(): Promise<{ run_id: string }> {
  const res = await fetch(`${API_BASE}/api/v1/analyze`, { method: 'POST' })
  if (!res.ok) throw new Error(`Trigger failed: ${res.status}`)
  return res.json()
}

export async function fetchRunStatus(runId: string): Promise<RunStatus> {
  const res = await fetch(`${API_BASE}/api/v1/runs/${runId}/status`)
  if (!res.ok) throw new Error(`Status fetch failed: ${res.status}`)
  return res.json()
}

export async function fetchResult(runId: string): Promise<PipelineResult> {
  const res = await fetch(`${API_BASE}/api/v1/runs/${runId}/result`)
  if (!res.ok) throw new Error(`Result fetch failed: ${res.status}`)
  return res.json()
}

export async function fetchLatestRun(): Promise<RunStatus | null> {
  const res = await fetch(`${API_BASE}/api/v1/runs`)
  if (!res.ok) return null
  const data = await res.json()
  const runs: RunStatus[] = Array.isArray(data) ? data : data.runs ?? []
  return runs.find(r => r.status === 'COMPLETE') ?? runs[0] ?? null
}

export async function fetchRuns(): Promise<RunStatus[]> {
  const res = await fetch(`${API_BASE}/api/v1/runs`)
  if (!res.ok) return []
  const data = await res.json()
  return Array.isArray(data) ? data : data.runs ?? []
}

export async function fetchAssets(): Promise<Asset[]> {
  const res = await fetch('/assets.json')
  if (!res.ok) throw new Error('Failed to load asset inventory')
  return res.json()
}
