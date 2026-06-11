import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import CandleChart, { type LiveCandle } from '../components/CandleChart'
import DepthPanel from '../components/DepthPanel'
import { INTERVALS, useMarketStore } from '../stores/market'
import { useTopic } from '../ws/hooks'

interface CandleMsg extends LiveCandle {
  type: string
  symbol: string
  interval: string
  closed: boolean
}

export default function ChartPage() {
  const { symbol, interval, setSymbol, setInterval } = useMarketStore()
  const [liveCandle, setLiveCandle] = useState<LiveCandle | null>(null)

  const symbolsQuery = useQuery({ queryKey: ['symbols'], queryFn: api.symbols })
  const candlesQuery = useQuery({
    queryKey: ['candles', symbol, interval],
    queryFn: () => api.candles(symbol, interval),
  })

  useTopic(`candles:${symbol}:${interval}`, (data) => {
    const msg = data as CandleMsg
    if (msg.symbol === symbol && msg.interval === interval) {
      setLiveCandle(msg)
    }
  })

  // Sub-second updates: move the forming candle's close with each trade tick.
  useTopic(`trades:${symbol}`, (data) => {
    const trade = data as { symbol: string; price: number }
    if (trade.symbol !== symbol) return
    setLiveCandle((prev) =>
      prev
        ? {
            ...prev,
            close: trade.price,
            high: Math.max(prev.high, trade.price),
            low: Math.min(prev.low, trade.price),
          }
        : prev,
    )
  })

  const symbols = symbolsQuery.data?.watchlist ?? ['BTCUSDT']

  return (
    <div className="flex h-[calc(100vh-10rem)] flex-col gap-3">
      <div className="flex items-center gap-3">
        <select
          aria-label="Symbol"
          value={symbol}
          onChange={(e) => {
            setSymbol(e.target.value)
            setLiveCandle(null)
          }}
          className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-sm"
        >
          {symbols.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <div className="flex gap-1" role="group" aria-label="Interval">
          {INTERVALS.map((iv) => (
            <button
              key={iv}
              onClick={() => {
                setInterval(iv)
                setLiveCandle(null)
              }}
              className={`rounded px-2 py-1 text-xs font-medium ${
                iv === interval
                  ? 'bg-emerald-600 text-white'
                  : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700'
              }`}
            >
              {iv}
            </button>
          ))}
        </div>
      </div>
      <div className="flex min-h-0 flex-1 gap-3">
        <div className="min-w-0 flex-1 rounded border border-zinc-800 bg-zinc-900/50 p-2">
          {candlesQuery.isLoading && (
            <p className="p-4 text-zinc-400" role="status">
              Loading candles…
            </p>
          )}
          {candlesQuery.isError && (
            <p className="p-4 text-red-400" role="alert">
              Failed to load candles: {String(candlesQuery.error)}
            </p>
          )}
          {candlesQuery.data && candlesQuery.data.candles.length === 0 && (
            <p className="p-4 text-zinc-400">
              No data for {symbol} {interval}. Run the backfill first.
            </p>
          )}
          {candlesQuery.data && candlesQuery.data.candles.length > 0 && (
            <CandleChart
              candles={candlesQuery.data.candles}
              liveCandle={liveCandle}
            />
          )}
        </div>
        <div className="hidden w-64 shrink-0 rounded border border-zinc-800 bg-zinc-900/50 lg:block">
          <DepthPanel symbol={symbol} />
        </div>
      </div>
    </div>
  )
}
