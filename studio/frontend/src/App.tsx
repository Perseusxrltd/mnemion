import { lazy, Suspense, useCallback, useEffect, useState, type ReactNode } from 'react'
import { BrowserRouter, HashRouter, Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom'
import Layout from './components/Layout'
import telemetryDisclosure from '../../../mnemion/product_telemetry/disclosure.json'

const Dashboard = lazy(() => import('./views/Dashboard'))
const GraphView = lazy(() => import('./views/GraphView'))
const Browser = lazy(() => import('./views/Browser'))
const SearchView = lazy(() => import('./views/SearchView'))
const DrawerDetail = lazy(() => import('./views/DrawerDetail'))
const AgentsView = lazy(() => import('./views/AgentsView'))
const ConnectorsView = lazy(() => import('./views/ConnectorsView'))
const SettingsView = lazy(() => import('./views/SettingsView'))
const CoreMemoryView = lazy(() => import('./views/CoreMemoryView'))
const Workspace = lazy(() => import('./workspace/Workspace'))
const Documentation = lazy(() => import('./workspace/Documentation'))
const HostedConsent = lazy(() => import('./workspace/HostedConsent'))
const HostControl = lazy(() => import('./workspace/HostControl'))
const Privacy = lazy(() => import('./workspace/Privacy'))
const TelemetrySetup = lazy(() => import('./workspace/TelemetrySetup'))

// Electron loads the app from file://, so HashRouter is required.
// In the browser dev server, BrowserRouter is fine.
const Router = window.location.protocol === 'file:' ? HashRouter : BrowserRouter

function lazyRoute(node: ReactNode) {
  return <Suspense fallback={<div className="min-h-[240px]" />}>{node}</Suspense>
}

function NativeNavigationBridge() {
  const navigate = useNavigate()

  useEffect(() => {
    return window.mnemion?.onNavigate?.((route) => navigate(route))
  }, [navigate])

  return null
}

function TelemetrySetupEntry() {
  const { pathname } = useLocation()
  const [finished, setFinished] = useState(false)
  const done = useCallback(() => setFinished(true), [])
  // Unavailable releases never load the setup controls or ask a native child
  // for privacy state. Documentation and OAuth consent are not app setup.
  if (finished || !telemetryDisclosure.collection_available || !telemetryDisclosure.destination ||
      ['/privacy', '/help', '/oauth/consent'].includes(pathname)) return null
  return <Suspense fallback={null}><TelemetrySetup onDone={done} /></Suspense>
}

export default function App() {
  return (
    <Router>
      <NativeNavigationBridge />
      <TelemetrySetupEntry />
      <Routes>
        <Route path="/oauth/consent" element={lazyRoute(<HostedConsent />)} />
        <Route path="/help" element={lazyRoute(<Documentation />)} />
        <Route path="/hosts" element={lazyRoute(<HostControl />)} />
        <Route path="/privacy" element={lazyRoute(<Privacy />)} />
        <Route path="/workspace/*" element={lazyRoute(<Workspace />)} />
        <Route index element={<Navigate to="/workspace" replace />} />
        <Route element={<Layout />}>
          <Route path="/dashboard" element={lazyRoute(<Dashboard />)} />
          <Route path="/graph" element={lazyRoute(<GraphView />)} />
          <Route path="/browse" element={lazyRoute(<Browser />)} />
          <Route path="/browse/:wing" element={lazyRoute(<Browser />)} />
          <Route path="/browse/:wing/:room" element={lazyRoute(<Browser />)} />
          <Route path="/drawer/*" element={lazyRoute(<DrawerDetail />)} />
          <Route path="/search" element={lazyRoute(<SearchView />)} />
          <Route path="/agents" element={lazyRoute(<AgentsView />)} />
          <Route path="/connect" element={lazyRoute(<ConnectorsView />)} />
          <Route path="/settings" element={lazyRoute(<SettingsView />)} />
          <Route path="/corememory" element={lazyRoute(<CoreMemoryView />)} />
        </Route>
      </Routes>
    </Router>
  )
}
