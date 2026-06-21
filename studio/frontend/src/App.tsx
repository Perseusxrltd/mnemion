import { lazy, Suspense, type ReactNode } from 'react'
import { BrowserRouter, HashRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'

const Dashboard = lazy(() => import('./views/Dashboard'))
const GraphView = lazy(() => import('./views/GraphView'))
const Browser = lazy(() => import('./views/Browser'))
const SearchView = lazy(() => import('./views/SearchView'))
const DrawerDetail = lazy(() => import('./views/DrawerDetail'))
const AgentsView = lazy(() => import('./views/AgentsView'))
const ConnectorsView = lazy(() => import('./views/ConnectorsView'))
const SettingsView = lazy(() => import('./views/SettingsView'))
const CoreMemoryView = lazy(() => import('./views/CoreMemoryView'))

// Electron loads the app from file:// — HashRouter required for routing to work.
// In the browser dev server, BrowserRouter is fine.
const Router = window.location.protocol === 'file:' ? HashRouter : BrowserRouter

function lazyRoute(node: ReactNode) {
  return <Suspense fallback={<div className="min-h-[240px]" />}>{node}</Suspense>
}

export default function App() {
  return (
    <Router>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
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
