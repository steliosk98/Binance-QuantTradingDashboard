import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import CandleChart, {
  type LiveCandle,
  type Overlay,
  type PaneSeries,
} from '../components/CandleChart'
import DepthPanel from '../components/DepthPanel'
import { INTERVALS, useMarketStore } from '../stores/market'
import { useTopic } from '../ws/hooks'

const INDICATOR_TOGGLES = [
  'SMA 20',
  'SMA 50',
  'EMA 20',
  'BB',
  'VWAP',
  'RSI',
  'MACD',
] as const
type IndicatorName = (typeof INDICATOR_TOGGLES)[number]

interface CandleMsg extends LiveCandle {
  type: string
  symbol: string
  interval: string
  closed: boolean
}

export default function ChartPage() {
  const { symbol, interval, setSymbol, setInterval } = useMarketStore()
  const [liveCandle, setLiveCandle] = useState<LiveCandle | null>(null)
  const [active, setActive] = useState<Set<IndicatorName>>(new Set())

  const symbolsQuery = useQuery({ queryKey: ['symbols'], queryFn: api.symbols })
  const candlesQuery = useQuery({
    queryKey: ['candles', symbol, interval],
    queryFn: () => api.candles(symbol, interval),
  })
  const indicatorsQuery = useQuery({
    queryKey: ['indicators', symbol, interval],
    queryFn: () => api.indicators(symbol, interval),
    enabled: active.size > 0,
  })

  const ind = indicatorsQuery.data
  const overlays: Overlay[] = []
  const paneSeries: PaneSeries[] = []
  if (ind) {
    if (active.has('SMA 20'))
      overlays.push({ id: 'sma20', color: '#60a5fa', data: ind.sma_20 })
    if (active.has('SMA 50'))
      overlays.push({ id: 'sma50', color: '#f59e0b', data: ind.sma_50 })
    if (active.has('EMA 20'))
      overlays.push({ id: 'ema20', color: '#a78bfa', data: ind.ema_20 })
    if (active.has('VWAP'))
      overlays.push({ id: 'vwap', color: '#f472b6', data: ind.vwap_session })
    if (active.has('BB')) {
      overlays.push({ id: 'bbu', color: '#52525b', data: ind.bb_upper })
      overlays.push({ id: 'bbm', color: '#71717a', data: ind.bb_middle })
      overlays.push({ id: 'bbl', color: '#52525b', data: ind.bb_lower })
    }
    let pane = 1
    if (active.has('RSI')) {
      paneSeries.push({ id: 'rsi', color: '#a78bfa', data: ind.rsi_14, pane })
      pane += 1
    }
    if (active.has('MACD')) {
      paneSeries.push({ id: 'macd', color: '#34d399', data: ind.macd, pane })
      paneSeries.push({
        id: 'macds',
        color: '#f87171',
        data: ind.macd_signal,
        pane,
      })
    }
  }

  const toggle = (name: IndicatorName) =>
    setActive((prev) => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
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
        <div className="flex gap-1" role="group" aria-label="Indicators">
          {INDICATOR_TOGGLES.map((name) => (
            <button
              key={name}
              onClick={() => toggle(name)}
              className={`rounded px-2 py-1 text-xs font-medium ${
                active.has(name)
                  ? 'bg-blue-600 text-white'
                  : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700'
              }`}
            >
              {name}
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
              overlays={overlays}
              paneSeries={paneSeries}
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
