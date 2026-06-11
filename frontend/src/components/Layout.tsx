import { NavLink, Outlet } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { useWsStatus } from '../ws/hooks'

const STATUS_STYLES = {
  open: { dot: 'bg-emerald-400', label: 'live' },
  connecting: { dot: 'bg-amber-400 animate-pulse', label: 'connecting' },
  closed: { dot: 'bg-red-400', label: 'offline' },
} as const

function WsIndicator() {
  const status = useWsStatus()
  const s = STATUS_STYLES[status]
  return (
    <span
      className="ml-auto flex items-center gap-1.5 text-xs text-zinc-400"
      data-testid="ws-status"
    >
      <span className={`h-2 w-2 rounded-full ${s.dot}`} />
      {s.label}
    </span>
  )
}

const NAV_ITEMS = [
  { to: '/', label: 'Dashboard' },
  { to: '/chart', label: 'Chart' },
  { to: '/research', label: 'Research' },
  { to: '/backtest', label: 'Backtest' },
  { to: '/paper', label: 'Paper Trading' },
  { to: '/portfolio', label: 'Portfolio' },
  { to: '/settings', label: 'Settings' },
]

export default function Layout() {
  const portfolioStatus = useQuery({
    queryKey: ['portfolio-status'],
    queryFn: api.portfolioStatus,
    retry: false,
  })
  const items = NAV_ITEMS.filter(
    (item) =>
      item.to !== '/portfolio' || portfolioStatus.data?.configured === true,
  )
  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-zinc-800 bg-zinc-900">
        <nav className="mx-auto flex max-w-7xl items-center gap-1 px-4 py-2">
          <span className="mr-6 text-lg font-bold text-emerald-400">
            CryptoQuant
          </span>
          {items.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) =>
                `rounded px-3 py-1.5 text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-zinc-800 text-emerald-400'
                    : 'text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100'
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
          <WsIndicator />
        </nav>
      </header>
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6">
        <Outlet />
      </main>
      <footer className="border-t border-zinc-800 px-4 py-3 text-center text-xs text-zinc-500">
        Research tool. Not financial advice. No live trading.
      </footer>
    </div>
  )
}
