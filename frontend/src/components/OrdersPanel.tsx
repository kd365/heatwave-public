import { useState } from 'react'
import type { DispatchOrder, Asset } from '../api'

interface Props {
  orders: DispatchOrder[]
  assets: Asset[]
}

const ROLE_COLORS: Record<string, string> = {
  primary:  '#ff6b35',
  cooling:  '#38bdf8',
  medical:  '#f472b6',
  staged:   '#a3e635',
  support:  '#a78bfa',
}

export function OrdersPanel({ orders, assets }: Props) {
  const [collapsed, setCollapsed] = useState(true)

  const assetMap = new Map(assets.map(a => [a.id, a]))

  const header = (
    <div className="orders-header" onClick={() => setCollapsed(c => !c)}>
      <span className="orders-title">DISPATCH ORDERS</span>
      {orders.length > 0 && (
        <span className="orders-count">{orders.length} order{orders.length !== 1 ? 's' : ''}</span>
      )}
      <span className="orders-toggle">{collapsed ? '▲' : '▼'}</span>
    </div>
  )

  if (collapsed) {
    return <div className="orders-panel orders-panel--collapsed">{header}</div>
  }

  return (
    <div className="orders-panel">
      {header}
      <div className="orders-body">
        {orders.length === 0 ? (
          <div className="orders-empty">No dispatch orders — run the pipeline to generate orders.</div>
        ) : (
          <table className="orders-table">
            <thead>
              <tr>
                <th>Asset</th>
                <th>Type</th>
                <th>Role</th>
                <th>Target Hex</th>
                <th>Distance (km)</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((o, i) => {
                const asset = assetMap.get(o.asset_id)
                const roleKey = (o.role ?? '').toLowerCase()
                const roleColor = ROLE_COLORS[roleKey] ?? '#888'
                return (
                  <tr key={i}>
                    <td className="orders-cell-asset">
                      <span className="orders-asset-id">{o.asset_id}</span>
                      {asset && <span className="orders-asset-desc">{asset.description}</span>}
                    </td>
                    <td>{asset ? formatType(asset.asset_type) : '—'}</td>
                    <td>
                      <span className="orders-role-badge" style={{ color: roleColor, borderColor: roleColor }}>
                        {o.role ?? '—'}
                      </span>
                    </td>
                    <td className="orders-cell-mono">{o.to_hex.slice(-8)}</td>
                    <td className="orders-cell-num">{o.distance != null ? o.distance.toFixed(1) : '—'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

function formatType(t: string): string {
  return t.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}
