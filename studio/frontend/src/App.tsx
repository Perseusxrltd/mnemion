import { BrowserRouter, HashRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './views/Dashboard'
import GraphView from './views/GraphView'
import Browser from './views/Browser'
import SearchView from './views/SearchView'
import DrawerDetail from './views/DrawerDetail'
import AgentsView from './views/AgentsView'
import ConnectorsView from './views/ConnectorsView'
import SettingsView from './views/SettingsView'

// Electron loads the app from file:// — HashRouter required for routing to work.
// In the browser dev server, BrowserRouter is fine.
const Router = window.location.protocol === 'file:' ? HashRouter : BrowserRouter

export default function App() {
  return (
    <Router>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/graph" element={<GraphView />} />
          <Route path="/browse" element={<Browser />} />
          <Route path="/browse/:wing" element={<Browser />} />
          <Route path="/browse/:wing/:room" element={<Browser />} />
          <Route path="/drawer/*" element={<DrawerDetail />} />
          <Route path="/search" element={<SearchView />} />
          <Route path="/agents" element={<AgentsView />} />
          <Route path="/connect" element={<ConnectorsView />} />
          <Route path="/settings" element={<SettingsView />} />
        </Route>
      </Routes>
    </Router>
  )
}
