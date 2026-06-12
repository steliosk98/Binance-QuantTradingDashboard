import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { useMarketStore } from '../stores/market'

interface Command {
  id: string
  label: string
  hint: string
  run: () => void
}

/** ⌘K / Ctrl+K command palette: pages, symbols, quick actions. */
export default function CommandPalette() {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const navigate = useNavigate()
  const setSymbol = useMarketStore((s) => s.setSymbol)
  const symbolsQuery = useQuery({ queryKey: ['symbols'], queryFn: api.symbols })

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setOpen((v) => !v)
        setQuery('')
        setActive(0)
      } else if (e.key === 'Escape') {
        setOpen(false)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  useEffect(() => {
    if (open) inputRef.current?.focus()
  }, [open])

  const commands = useMemo<Command[]>(() => {
    const go = (path: string) => () => {
      navigate(path)
      setOpen(false)
    }
    const pages: Command[] = [
      { id: 'p-dash', label: 'Dashboard', hint: 'page', run: go('/') },
      { id: 'p-chart', label: 'Chart', hint: 'page', run: go('/chart') },
      {
        id: 'p-research',
        label: 'Research',
        hint: 'page',
        run: go('/research'),
      },
      {
        id: 'p-backtest',
        label: 'Backtest',
        hint: 'page',
        run: go('/backtest'),
      },
      {
        id: 'p-paper',
        label: 'Paper Trading',
        hint: 'page',
        run: go('/paper'),
      },
      { id: 'p-alerts', label: 'Alerts', hint: 'page', run: go('/alerts') },
      {
        id: 'p-settings',
        label: 'Settings',
        hint: 'page',
        run: go('/settings'),
      },
    ]
    const symbols: Command[] = (symbolsQuery.data?.watchlist ?? []).map(
      (s) => ({
        id: `s-${s}`,
        label: `Chart ${s.replace('USDT', '')}/USDT`,
        hint: 'symbol',
        run: () => {
          setSymbol(s)
          navigate('/chart')
          setOpen(false)
        },
      }),
    )
    return [...pages, ...symbols]
  }, [navigate, setSymbol, symbolsQuery.data])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return commands
    return commands.filter((c) => c.label.toLowerCase().includes(q))
  }, [commands, query])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-100 flex items-start justify-center bg-black/60 pt-[18vh] backdrop-blur-sm"
      onClick={() => setOpen(false)}
      data-testid="command-palette"
    >
      <div
        className="w-[480px] overflow-hidden rounded-sm border border-zinc-700 bg-zinc-900 shadow-2xl shadow-black/60"
        onClick={(e) => e.stopPropagation()}
      >
        <input
          ref={inputRef}
          aria-label="Command"
          value={query}
          placeholder="Jump to page or symbol…"
          onChange={(e) => {
            setQuery(e.target.value)
            setActive(0)
          }}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') {
              e.preventDefault()
              setActive((a) => Math.min(a + 1, filtered.length - 1))
            } else if (e.key === 'ArrowUp') {
              e.preventDefault()
              setActive((a) => Math.max(a - 1, 0))
            } else if (e.key === 'Enter' && filtered[active]) {
              filtered[active].run()
            }
          }}
          className="w-full border-b border-zinc-800 bg-transparent px-4 py-3 font-mono text-sm text-zinc-100 outline-none placeholder:text-zinc-600"
        />
        <ul className="max-h-72 overflow-y-auto py-1">
          {filtered.length === 0 && (
            <li className="px-4 py-3 font-mono text-xs text-zinc-600">
              No matches.
            </li>
          )}
          {filtered.map((c, i) => (
            <li key={c.id}>
              <button
                onClick={c.run}
                onMouseEnter={() => setActive(i)}
                className={`flex w-full cursor-pointer items-center justify-between px-4 py-1.5 text-left text-sm ${
                  i === active
                    ? 'bg-amber-400/10 text-amber-400'
                    : 'text-zinc-300'
                }`}
              >
                {c.label}
                <span className="font-mono text-[10px] tracking-[0.12em] text-zinc-600 uppercase">
                  {c.hint}
                </span>
              </button>
            </li>
          ))}
        </ul>
        <div className="border-t border-zinc-800 px-4 py-1.5 font-mono text-[10px] text-zinc-600">
          ↑↓ navigate · ↵ select · esc close
        </div>
      </div>
    </div>
  )
}
