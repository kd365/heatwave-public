import 'leaflet/dist/leaflet.css'
import { MapContainer, TileLayer } from 'react-leaflet'
import './App.css'

// Dallas city center
const DALLAS_CENTER: [number, number] = [32.7767, -96.797]
const DEFAULT_ZOOM = 11

function App() {
  return (
    <div className="app-layout">
      <header className="app-header">
        <h1>🌡️ HEATWAVE</h1>
        <span className="app-subtitle">Dallas Heat Emergency Response — Aug 2023</span>
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
        </MapContainer>
      </main>
    </div>
  )
}

export default App
