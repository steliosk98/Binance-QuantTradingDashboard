import { useState } from 'react'
import Panel from './Panel'
import { useTopic } from '../ws/hooks'

interface LiqEvent {
  symbol: string
  ts: number
  side: 'long' | 'short'
  price: number
  qty: number
  value: number
}

interface TradeEvent {
  symbol: string
  ts: number
  price: number
  qty: number
  value: number
  is_buyer_maker: boolean
}

const MAX_ROWS = 30

function fmtUsd(v: number): string {
  return Intl.NumberFormat(undefined, {
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(v)
}

function fmtTime(ts: number): string {
  return new Date(ts).toISOString().slice(11, 19)
}

export function LiquidationFeed() {
  const [events, setEvents] = useState<LiqEvent[]>([])
  useTopic('liqs', (data) => {
    setEvents((prev) => [data as LiqEvent, ...prev].slice(0, MAX_ROWS))
  })
  return (
    <Panel
      title="Liquidations"
      status={events.length ? 'live' : 'idle'}
      testId="liq-feed"
    >
      <div className="max-h-56 overflow-y-auto font-mono text-[11px]">
        {events.length === 0 && (
          <p className="px-3 py-3 text-zinc-600">Awaiting liquidations…</p>
        )}
        {events.map((e, i) => (
          <div
            key={`${e.ts}${i}`}
            className={`flex items-center justify-between border-l-2 px-3 py-1 tabular-nums ${
              e.side === 'long' ? 'border-red-500/60' : 'border-emerald-400/60'
            }`}
          >
            <span className="text-zinc-600">{fmtTime(e.ts)}</span>
            <span className="font-medium text-zinc-300">
              {e.symbol.replace('USDT', '')}
            </span>
            <span
              className={
                e.side === 'long' ? 'text-red-400' : 'text-emerald-400'
              }
            >
              {e.side.toUpperCase()} LIQ
            </span>
            <span className="text-zinc-100">${fmtUsd(e.value)}</span>
          </div>
        ))}
      </div>
    </Panel>
  )
}

export function WhaleFeed() {
  const [events, setEvents] = useState<TradeEvent[]>([])
  useTopic('whales', (data) => {
    setEvents((prev) => [data as TradeEvent, ...prev].slice(0, MAX_ROWS))
  })
  return (
    <Panel
      title="Whale Trades"
      status={events.length ? 'live' : 'idle'}
      testId="whale-feed"
    >
      <div className="max-h-56 overflow-y-auto font-mono text-[11px]">
        {events.length === 0 && (
          <p className="px-3 py-3 text-zinc-600">Awaiting whale trades…</p>
        )}
        {events.map((e, i) => (
          <div
            key={`${e.ts}${i}`}
            className={`flex items-center justify-between border-l-2 px-3 py-1 tabular-nums ${
              e.is_buyer_maker ? 'border-red-500/60' : 'border-emerald-400/60'
            }`}
          >
            <span className="text-zinc-600">{fmtTime(e.ts)}</span>
            <span className="font-medium text-zinc-300">
              {e.symbol.replace('USDT', '')}
            </span>
            <span
              className={e.is_buyer_maker ? 'text-red-400' : 'text-emerald-400'}
            >
              {e.is_buyer_maker ? 'SELL' : 'BUY'}
            </span>
            <span className="text-zinc-100">${fmtUsd(e.value)}</span>
          </div>
        ))}
      </div>
    </Panel>
  )
}
