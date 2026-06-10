import { NavLink, Outlet } from 'react-router-dom'

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
  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-zinc-800 bg-zinc-900">
        <nav className="mx-auto flex max-w-7xl items-center gap-1 px-4 py-2">
          <span className="mr-6 text-lg font-bold text-emerald-400">
            CryptoQuant
          </span>
          {NAV_ITEMS.map((item) => (
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
