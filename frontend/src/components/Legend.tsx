import { useState } from 'react'
import type { HexEvent, ThreatScore, RunStatus } from '../api'

interface Props {
  hexEvents: HexEvent[]
  threatMap?: ThreatScore[]
  runStatus: RunStatus | null
}

export function Legend({ hexEvents, threatMap = [], runStatus }: Props) {
  const [collapsed, setCollapsed] = useState(false)
  const counts = { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0, UNSCORED: 0 }
  const threatLookup = new Map(threatMap.map(t => [t.hex_id, t]))
  for (const h of hexEvents) {
    const t = threatLookup.get(h.hex_id)
    const level = (t?.risk_level ?? 'UNSCORED') as keyof typeof counts
    if (level in counts) counts[level]++
    else counts.UNSCORED++
  }
  const multiSource = hexEvents.filter(h => h.source_count >= 2).length

  return (
    <div className={`legend${collapsed ? ' legend--collapsed' : ''}`}>
      <div className="legend-title">
        HEATWAVE Threat Map
        <button
          className="legend-toggle"
          onClick={() => setCollapsed(c => !c)}
          title={collapsed ? 'Expand' : 'Collapse'}
        >
          {collapsed ? '▲' : '▼'}
        </button>
      </div>
      {!collapsed && (
        <>
          <div className="legend-items">
            <LegendRow color="#dc2626" label="CRITICAL" threshold="≥0.85" count={counts.CRITICAL} />
            <LegendRow color="#ea580c" label="HIGH"     threshold="≥0.65" count={counts.HIGH} />
            <LegendRow color="#eab308" label="MEDIUM"   threshold="≥0.40" count={counts.MEDIUM} />
            <LegendRow color="#16a34a" label="LOW"      threshold="<0.40"  count={counts.LOW} />
          </div>
          {hexEvents.length > 0 && (
            <div className="legend-stats">
              <div>{hexEvents.length} hexes | {counts.HIGH} HIGH | {counts.MEDIUM} MEDIUM | {counts.LOW} LOW</div>
              {multiSource > 0 && <div>{multiSource} multi-source hexes</div>}
              {runStatus && (
                <div>
                  {runStatus.tokens_used > 0 && `${Math.round(runStatus.tokens_used / 1000)}K tokens`}
                  {runStatus.duration_ms && ` | ${(runStatus.duration_ms / 60000).toFixed(1)} min`}
                  {' | 3 agents'}
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}

function LegendRow({ color, label, threshold, count }: {
  color: string; label: string; threshold: string; count: number
}) {
  return (
    <div className="legend-row">
      <span className="legend-swatch" style={{ background: color }} />
      <span className="legend-label">{label} ({threshold})</span>
      {count > 0 && <span className="legend-count">{count}</span>}
    </div>
  )
}
