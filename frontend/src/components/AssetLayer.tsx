import { useMemo } from 'react'
import { Marker, Tooltip } from 'react-leaflet'
import L from 'leaflet'
import { cellToLatLng } from 'h3-js'
import type { Asset, DispatchOrder } from '../api'

// Pre-create icons at module level (avoids re-creating on every render)
function makeIcon(emoji: string, size = 18) {
  return L.divIcon({
    html: `<span style="font-size:${size}px;line-height:1;filter:drop-shadow(0 1px 3px rgba(0,0,0,0.9))">${emoji}</span>`,
    className: '',  // important: removes Leaflet's default white box
    iconSize: [size + 6, size + 6],
    iconAnchor: [(size + 6) / 2, (size + 6) / 2],
    tooltipAnchor: [(size + 6) / 2, -(size / 2)],
  })
}

// Activated cooling center: bigger emoji + animated cyan pulse ring
const COOLING_ACTIVE_ICON = L.divIcon({
  html: `
    <div style="position:relative;width:36px;height:36px;display:flex;align-items:center;justify-content:center">
      <span style="
        position:absolute;inset:0;border-radius:50%;
        border:2px solid #22d3ee;
        animation:ccPulse 1.6s ease-out infinite;
      "></span>
      <span style="font-size:24px;line-height:1;filter:drop-shadow(0 0 6px #22d3ee);">❄️</span>
    </div>`,
  className: '',
  iconSize: [36, 36],
  iconAnchor: [18, 18],
  tooltipAnchor: [18, -16],
})

const ICONS = {
  cooling:   makeIcon('❄️'),
  ambulance: makeIcon('🚑'),
  medical:   makeIcon('🏥'),
  outreach:  makeIcon('🚐'),
  staged:    makeIcon('📍'),
}

function mobileIcon(assetType: string) {
  if (assetType.includes('ambulance') || assetType.includes('rescue') || assetType === 'medic1_suv') {
    return ICONS.ambulance
  }
  if (assetType === 'mobile_medical_unit') return ICONS.medical
  return ICONS.outreach
}

function assetLabel(assetType: string): string {
  const labels: Record<string, string> = {
    ambulance_als: 'ALS Ambulance',
    ambulance_als_peak: 'ALS Ambulance (peak)',
    cooling_center_library: 'Cooling Center (Library)',
    cooling_center_recreation: 'Cooling Center (Rec)',
    dart_cares_unit: 'DART CARES Unit',
    medic1_suv: 'Medic 1 SUV',
    mini_ambulance: 'Mini Ambulance',
    mobile_medical_unit: 'Mobile Medical Unit',
    modss_outreach: 'MODSS Outreach',
    right_care_unit: 'RIGHT Care Unit',
    special_event_rescue: 'Special Event Rescue',
  }
  return labels[assetType] ?? assetType
}

interface Props {
  assets: Asset[]
  orders: DispatchOrder[]
  activatedCoolingIds: string[]
}

export function AssetLayer({ assets, orders, activatedCoolingIds }: Props) {
  const assetById = useMemo(() => new Map(assets.map(a => [a.id, a])), [assets])
  const activatedSet = useMemo(() => new Set(activatedCoolingIds), [activatedCoolingIds])

  const coolingCenters = useMemo(
    () => assets.filter(a => a.asset_type.startsWith('cooling_center')),
    [assets]
  )

  return (
    <>
      {/* Cooling centers — always visible at fixed home location */}
      {coolingCenters.map(cc => {
        const activated = activatedSet.has(cc.id)
        return (
          <Marker
            key={cc.id}
            position={[cc.home_lat, cc.home_lon]}
            icon={activated ? COOLING_ACTIVE_ICON : ICONS.cooling}
            opacity={activated ? 1.0 : 0.35}
            zIndexOffset={activated ? 200 : 0}
          >
            <Tooltip direction="top">
              <div style={{ fontSize: '0.8rem', lineHeight: 1.6 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                  <strong>{cc.id}</strong>
                  <span style={{
                    padding: '1px 6px', borderRadius: 3, fontSize: '0.7rem', fontWeight: 700,
                    background: activated ? '#164e63' : '#374151',
                    color:      activated ? '#22d3ee'  : '#9ca3af',
                  }}>
                    {activated ? '❄ ACTIVATED' : 'INACTIVE'}
                  </span>
                </div>
                <div>{assetLabel(cc.asset_type)}</div>
                <div><strong>Address:</strong> {cc.home_address}</div>
                <div><strong>Capacity:</strong> {cc.capacity} persons</div>
                <div><strong>Hours:</strong> {cc.shift === 'business_hours' ? 'Business hours' : '24hr'}</div>
              </div>
            </Tooltip>
          </Marker>
        )
      })}

      {/* Dispatched / staged mobile assets — jittered when multiple orders share a hex */}
      {(() => {
        // Group orders by to_hex so we can compute offsets for stacked assets
        const hexCount = new Map<string, number>()
        const hexIndex = new Map<string, number>()
        for (const o of orders) {
          hexCount.set(o.to_hex, (hexCount.get(o.to_hex) ?? 0) + 1)
          hexIndex.set(o.to_hex, 0)
        }
        // Offsets: center first, then a ring of 6 positions matching hex geometry
        const OFFSETS: [number, number][] = [
          [0, 0],
          [0.0013, 0],
          [-0.0013, 0],
          [0, 0.0018],
          [0, -0.0018],
          [0.0013, 0.0018],
          [-0.0013, -0.0018],
        ]
        return orders.map((order, i) => {
          const idx = hexIndex.get(order.to_hex)!
          hexIndex.set(order.to_hex, idx + 1)
          const [dLat, dLng] = OFFSETS[Math.min(idx, OFFSETS.length - 1)]
        const asset = assetById.get(order.asset_id)
        const assetType = asset?.asset_type ?? ''
          const [baseLat, baseLng] = cellToLatLng(order.to_hex)
          const lat = baseLat + dLat
          const lng = baseLng + dLng
        const icon = order.role === 'stage' ? ICONS.staged : mobileIcon(assetType)
        const roleColor = order.role === 'stage'
          ? { bg: '#713f12', text: '#fef08a' }
          : { bg: '#7c2d12', text: '#fed7aa' }

        return (
          <Marker
            key={`order-${i}`}
            position={[lat, lng]}
            icon={icon}
          >
            <Tooltip direction="top" offset={[0, -12]}>
              <div style={{ fontSize: '0.8rem', lineHeight: 1.6 }}>
                <div>
                  <strong>{order.asset_id}</strong>
                  <span style={{ marginLeft: 6, padding: '1px 5px', borderRadius: 3,
                    background: roleColor.bg, color: roleColor.text,
                    fontSize: '0.7rem', fontWeight: 600 }}>
                    {order.role.toUpperCase()}
                  </span>
                </div>
                <div>{assetLabel(assetType)}</div>
                <div><strong>Distance:</strong> {order.distance} hex ring{order.distance !== 1 ? 's' : ''}</div>
                <div><strong>Assigned hex:</strong> …{order.to_hex.slice(-8)}</div>
              </div>
            </Tooltip>
          </Marker>
        )
        })
      })()}
    </>
  )
}
