import { useNavigate, useLocation } from 'react-router-dom'
import { LayoutDashboard, Network, FolderOpen, Search, Bot, Settings } from 'lucide-react'

const ITEMS = [
  { to: '/dashboard', icon: LayoutDashboard, title: 'Dashboard' },
  { to: '/graph',     icon: Network,         title: 'Graph' },
  { to: '/browse',    icon: FolderOpen,      title: 'Browse' },
  { to: '/search',    icon: Search,          title: 'Search' },
  { to: '/agents',    icon: Bot,             title: 'Agents' },
]

export default function Ribbon({ onSearch }: { onSearch?: () => void }) {
  const navigate = useNavigate()
  const { pathname } = useLocation()

  return (
    <div className="ribbon">
      {/* Mnemion logo */}
      <div className="ribbon-icon mb-2" title="Mnemion Studio">
        <span style={{ fontSize: 18, lineHeight: 1 }}>🏛</span>
      </div>

      <div className="w-6 h-px mb-2" style={{ background: 'var(--background-modifier-border)' }} />

      {ITEMS.map(({ to, icon: Icon, title }) => {
        const active = pathname.startsWith(to)
        return (
          <button
            key={to}
            className={`ribbon-icon ${active ? 'active' : ''}`}
            title={title}
            onClick={() => {
              if (to === '/search' && onSearch) { onSearch(); return }
              navigate(to)
            }}
          >
            <Icon size={18} />
          </button>
        )
      })}

      {/* Spacer */}
      <div className="flex-1" />

      <div className="w-6 h-px mb-2" style={{ background: 'var(--background-modifier-border)' }} />

      <button
        className={`ribbon-icon ${pathname.startsWith('/settings') ? 'active' : ''}`}
        title="Settings"
        onClick={() => navigate('/settings')}
      >
        <Settings size={18} />
      </button>
    </div>
  )
}
