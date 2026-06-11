import { useState } from 'react'
import { useTopic } from '../ws/hooks'

interface LiveTicker {
  symbol: string
  last: number
  change_pct: number
}

/** Streaming price strip across the top — pauses on hover. */
export default function TickerTape() {
  const [tickers, setTickers] = useState<Record<string, LiveTicker>>({})
  useTopic('tickers', (data) => {
    const msg = data as { tickers: LiveTicker[] }
    setTickers((prev) => {
      const next = { ...prev }
      for (const t of msg.tickers) next[t.symbol] = t
      return next
    })
  })

  const entries = Object.values(tickers).sort((a, b) =>
    a.symbol.localeCompare(b.symbol),
  )
  if (entries.length === 0) {
    return (
      <div
        className="h-7 border-b border-zinc-800 bg-zinc-900/60"
        data-testid="ticker-tape"
      />
    )
  }
  // Duplicate the run so the -50% translation loops seamlessly.
  const run = [...entries, ...entries]
  return (
    <div
      className="relative h-7 overflow-hidden border-b border-zinc-800 bg-zinc-900/60"
      data-testid="ticker-tape"
      role="marquee"
      aria-label="live watchlist prices"
    >
      <div className="ticker-track flex w-max items-center gap-8 px-4 leading-7 whitespace-nowrap">
        {run.map((t, i) => (
          <span
            key={`${t.symbol}-${i}`}
            className="font-mono text-[11px] tabular-nums"
          >
            <span className="text-zinc-400">
              {t.symbol.replace('USDT', '')}
            </span>{' '}
            <span className="text-zinc-100">
              {t.last >= 100
                ? t.last.toLocaleString(undefined, { maximumFractionDigits: 2 })
                : t.last.toPrecision(5)}
            </span>{' '}
            <span
              className={
                t.change_pct >= 0 ? 'text-emerald-400' : 'text-red-400'
              }
            >
              {t.change_pct >= 0 ? '▲' : '▼'}{' '}
              {Math.abs(t.change_pct).toFixed(2)}%
            </span>
          </span>
        ))}
      </div>
    </div>
  )
}
