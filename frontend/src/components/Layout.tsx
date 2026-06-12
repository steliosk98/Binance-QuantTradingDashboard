import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { useAuthStore } from '../stores/auth'
import AlertBell from './AlertBell'
import TickerTape from './TickerTape'
import { useWsStatus } from '../ws/hooks'

const NAV_ITEMS = [
  { to: '/', label: 'Dashboard' },
  { to: '/chart', label: 'Chart' },
  { to: '/research', label: 'Research' },
  { to: '/backtest', label: 'Backtest' },
  { to: '/paper', label: 'Paper Trading' },
  { to: '/alerts', label: 'Alerts' },
  { to: '/portfolio', label: 'Portfolio' },
  { to: '/settings', label: 'Settings' },
]

const STATUS_STYLES = {
  open: {
    dot: 'animate-pulse-dot bg-emerald-400',
    label: 'LIVE',
    text: 'text-emerald-400',
  },
  connecting: {
    dot: 'animate-pulse bg-amber-400',
    label: 'SYNC',
    text: 'text-amber-400',
  },
  closed: { dot: 'bg-red-500', label: 'OFFLINE', text: 'text-red-400' },
} as const

function WsIndicator() {
  const status = useWsStatus()
  const s = STATUS_STYLES[status]
  return (
    <span
      className="flex items-center gap-1.5 font-mono text-[10px] tracking-[0.12em]"
      data-testid="ws-status"
    >
      <span className={`h-1.5 w-1.5 rounded-full ${s.dot}`} />
      <span className={s.text}>{s.label}</span>
    </span>
  )
}

function UtcClock() {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])
  return (
    <time
      className="hidden font-mono text-[10px] tracking-[0.12em] text-zinc-500 tabular-nums md:block"
      dateTime={now.toISOString()}
    >
      {now.toISOString().slice(11, 19)} UTC
    </time>
  )
}

function LogoutButton() {
  const authQuery = useQuery({
    queryKey: ['auth-status'],
    queryFn: api.authStatus,
  })
  const clear = useAuthStore((s) => s.clear)
  if (!authQuery.data?.auth_enabled) return null
  return (
    <button
      onClick={clear}
      className="cursor-pointer rounded-sm px-2 py-0.5 font-mono text-[10px] tracking-[0.12em] text-zinc-500 uppercase transition-colors hover:bg-zinc-800 hover:text-red-400"
      aria-label="Sign out"
    >
      Exit
    </button>
  )
}

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
      <header className="sticky top-0 z-40 border-b border-zinc-800 bg-zinc-950/90 backdrop-blur">
        <nav className="flex items-center gap-1 overflow-x-auto px-4 py-2 whitespace-nowrap">
          <NavLink to="/" className="mr-5 flex items-baseline gap-1.5">
            <span className="font-display text-base font-bold tracking-tight text-zinc-100">
              CRYPTO<span className="text-amber-400">QUANT</span>
            </span>
            <span className="hidden font-mono text-[9px] tracking-[0.2em] text-zinc-600 sm:block">
              TERMINAL
            </span>
          </NavLink>
          {items.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) =>
                `cursor-pointer rounded-sm px-2.5 py-1 font-mono text-[11px] tracking-[0.08em] uppercase transition-colors duration-150 ${
                  isActive
                    ? 'bg-amber-400/10 text-amber-400'
                    : 'text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200'
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
          <div className="ml-auto flex items-center gap-4">
            <UtcClock />
            <AlertBell />
            <WsIndicator />
            <LogoutButton />
          </div>
        </nav>
        <TickerTape />
      </header>
      <main className="w-full min-w-0 flex-1 overflow-x-clip px-4 py-4 2xl:px-6">
        <Outlet />
      </main>
      <footer className="border-t border-zinc-800 px-4 py-2 text-center font-mono text-[10px] tracking-[0.1em] text-zinc-600 uppercase">
        Research tool · Not financial advice · No live trading
      </footer>
    </div>
  )
}
