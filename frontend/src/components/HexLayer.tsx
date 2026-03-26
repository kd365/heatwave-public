import { cellToBoundary } from 'h3-js'
import { Polygon, Tooltip } from 'react-leaflet'
import type { HexEvent } from '../api'

const RISK_COLORS: Record<string, string> = {
  CRITICAL: '#dc2626',
  HIGH:     '#ea580c',
  MEDIUM:   '#eab308',
  LOW:      '#16a34a',
  UNSCORED: '#9e9e9e',
}

interface ThreatScore {
  hex_id: string
  risk_level: string
  risk_score: number
}

interface Props {
  hexEvents: HexEvent[]
  threatMap?: ThreatScore[]
}

export function HexLayer({ hexEvents, threatMap = [] }: Props) {
  const threatLookup = new Map(threatMap.map(t => [t.hex_id, t]))

  return (
    <>
      {hexEvents.map((hex) => {
        const boundary = cellToBoundary(hex.hex_id) as [number, number][]
        const threat = threatLookup.get(hex.hex_id)
        const level = threat?.risk_level ?? 'UNSCORED'
        const score = threat?.risk_score ?? 0
        const color = RISK_COLORS[level] ?? RISK_COLORS.UNSCORED

        return (
          <Polygon
            key={hex.hex_id}
            positions={boundary}
            pathOptions={{
              color,
              fillColor: color,
              fillOpacity: level === 'CRITICAL' ? 0.7 : level === 'HIGH' ? 0.55 : level === 'MEDIUM' ? 0.4 : 0.2,
              weight: 1,
              opacity: 0.7,
            }}
          >
            <Tooltip sticky>
              <div style={{ fontSize: '0.8rem', lineHeight: 1.5 }}>
                <div><strong>Hex:</strong> {hex.hex_id}</div>
                <div><strong>Risk:</strong> <span style={{ color }}>{level}</span> ({score.toFixed(3)})</div>
                <div><strong>Temp:</strong> {hex.max_temp_f}°F (apparent: {hex.max_apparent_f}°F)</div>
                <div><strong>Hot days:</strong> {hex.hot_days} | <strong>Wx source:</strong> {hex.weather_source}</div>
                <div><strong>911:</strong> {hex.dispatch_count} | <strong>311:</strong> {hex.service_count} | <strong>Social:</strong> {hex.social_count}</div>
                {hex.dispatch_incidents?.length > 0 && (
                  <div><strong>911 details:</strong> {hex.dispatch_incidents.slice(0, 2).join('; ')}</div>
                )}
                {hex.social_signals?.length > 0 && (
                  <div><strong>Social:</strong> {hex.social_signals[0]?.slice(0, 80)}...</div>
                )}
                {Object.keys(hex.service_types ?? {}).length > 0 && (
                  <div><strong>311 types:</strong> {Object.entries(hex.service_types).map(([k, v]) => `${k.split(' - ')[0]}: ${v}`).join(', ')}</div>
                )}
              </div>
            </Tooltip>
          </Polygon>
        )
      })}
    </>
  )
}
