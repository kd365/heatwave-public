import { cellToBoundary } from 'h3-js'
import { Polygon, Tooltip } from 'react-leaflet'
import type { HexEvent } from '../api'

const RISK_COLORS: Record<string, string> = {
  CRITICAL: '#dc2626',
  HIGH:     '#ea580c',
  MEDIUM:   '#eab308',
  LOW:      '#16a34a',
}

function riskLevel(score: number): string {
  if (score >= 0.85) return 'CRITICAL'
  if (score >= 0.65) return 'HIGH'
  if (score >= 0.40) return 'MEDIUM'
  return 'LOW'
}

function hexColor(score: number): string {
  return RISK_COLORS[riskLevel(score)]
}

interface Props {
  hexEvents: HexEvent[]
}

export function HexLayer({ hexEvents }: Props) {
  return (
    <>
      {hexEvents.map((hex) => {
        // h3-js returns [lat, lng] pairs — Leaflet wants the same
        const boundary = cellToBoundary(hex.hex_id) as [number, number][]
        const color = hexColor(hex.severity_score)
        const level = riskLevel(hex.severity_score)

        return (
          <Polygon
            key={hex.hex_id}
            positions={boundary}
            pathOptions={{
              color,
              fillColor: color,
              fillOpacity: 0.45,
              weight: 1,
              opacity: 0.7,
            }}
          >
            <Tooltip sticky>
              <div style={{ fontSize: '0.8rem', lineHeight: 1.5 }}>
                <div><strong>Hex:</strong> {hex.hex_id}</div>
                <div><strong>Risk:</strong> <span style={{ color }}>{level}</span></div>
                <div><strong>Severity:</strong> {hex.severity_score.toFixed(3)}</div>
                <div><strong>Sources:</strong> {hex.sources.join(', ')}</div>
                {hex.weather_max_temp > 0 && (
                  <div><strong>Weather:</strong> {hex.weather_count} events (max {hex.weather_max_temp.toFixed(1)}°F)</div>
                )}
                <div><strong>911:</strong> {hex.dispatch_count}</div>
                <div><strong>311:</strong> {hex.service_count}</div>
                <div><strong>Social:</strong> {hex.social_count}</div>
              </div>
            </Tooltip>
          </Polygon>
        )
      })}
    </>
  )
}
