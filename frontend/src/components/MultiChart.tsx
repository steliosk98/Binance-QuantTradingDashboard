import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import CandleChart, { type LiveCandle } from './CandleChart'
import Panel from './Panel'
import { useTopic } from '../ws/hooks'

function MiniChart({
  initialSymbol,
  interval,
  symbols,
}: {
  initialSymbol: string
  interval: string
  symbols: string[]
}) {
  const [symbol, setSymbol] = useState(initialSymbol)
  const [live, setLive] = useState<LiveCandle | null>(null)
  const candlesQuery = useQuery({
    queryKey: ['candles', symbol, interval],
    queryFn: () => api.candles(symbol, interval, 300),
  })
  useTopic(`candles:${symbol}:${interval}`, (data) => {
    const msg = data as LiveCandle & { symbol: string; interval: string }
    if (msg.symbol === symbol && msg.interval === interval) setLive(msg)
  })

  return (
    <Panel
      title={`${symbol.replace('USDT', '')}/USDT · ${interval}`}
      status="live"
      right={
        <select
          aria-label={`Symbol for pane`}
          value={symbol}
          onChange={(e) => {
            setSymbol(e.target.value)
            setLive(null)
          }}
          className="rounded-sm border border-zinc-700 bg-zinc-950/60 px-1 py-0.5 font-mono text-[11px]"
        >
          {symbols.map((s) => (
            <option key={s} value={s}>
              {s.replace('USDT', '')}
            </option>
          ))}
        </select>
      }
      className="flex min-h-0 flex-col"
    >
      <div className="h-64 p-1">
        {candlesQuery.data && candlesQuery.data.candles.length > 0 ? (
          <CandleChart candles={candlesQuery.data.candles} liveCandle={live} />
        ) : (
          <p className="p-3 font-mono text-xs text-zinc-600" role="status">
            Loading…
          </p>
        )}
      </div>
    </Panel>
  )
}

/** 2×2 synchronized-interval multi-chart grid. */
export default function MultiChart({ interval }: { interval: string }) {
  const symbolsQuery = useQuery({ queryKey: ['symbols'], queryFn: api.symbols })
  const symbols = symbolsQuery.data?.watchlist ?? [
    'BTCUSDT',
    'ETHUSDT',
    'SOLUSDT',
    'BNBUSDT',
  ]
  const defaults = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT'].filter((s) =>
    symbols.includes(s),
  )
  while (defaults.length < 4 && symbols[defaults.length])
    defaults.push(symbols[defaults.length])

  return (
    <div className="grid flex-1 gap-3 lg:grid-cols-2" data-testid="multi-chart">
      {defaults.slice(0, 4).map((s, i) => (
        <MiniChart
          key={`${s}-${i}`}
          initialSymbol={s}
          interval={interval}
          symbols={symbols}
        />
      ))}
    </div>
  )
}
