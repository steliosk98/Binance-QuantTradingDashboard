import { useState } from 'react'
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
  return new Date(ts).toLocaleTimeString()
}

export function LiquidationFeed() {
  const [events, setEvents] = useState<LiqEvent[]>([])
  useTopic('liqs', (data) => {
    setEvents((prev) => [data as LiqEvent, ...prev].slice(0, MAX_ROWS))
  })
  return (
    <div className="rounded border border-zinc-800" data-testid="liq-feed">
      <div className="border-b border-zinc-800 px-3 py-2 text-sm font-medium">
        Liquidations
      </div>
      <div className="max-h-64 overflow-y-auto text-xs">
        {events.length === 0 && (
          <p className="px-3 py-3 text-zinc-500">Waiting for liquidations…</p>
        )}
        {events.map((e, i) => (
          <div key={`${e.ts}${i}`} className="flex justify-between px-3 py-1">
            <span className="text-zinc-400">{fmtTime(e.ts)}</span>
            <span className="font-medium">{e.symbol}</span>
            <span
              className={
                e.side === 'long' ? 'text-red-400' : 'text-emerald-400'
              }
            >
              {e.side} liq
            </span>
            <span className="tabular-nums text-zinc-300">
              ${fmtUsd(e.value)}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

export function WhaleFeed() {
  const [events, setEvents] = useState<TradeEvent[]>([])
  useTopic('whales', (data) => {
    setEvents((prev) => [data as TradeEvent, ...prev].slice(0, MAX_ROWS))
  })
  return (
    <div className="rounded border border-zinc-800" data-testid="whale-feed">
      <div className="border-b border-zinc-800 px-3 py-2 text-sm font-medium">
        Whale Trades
      </div>
      <div className="max-h-64 overflow-y-auto text-xs">
        {events.length === 0 && (
          <p className="px-3 py-3 text-zinc-500">Waiting for whale trades…</p>
        )}
        {events.map((e, i) => (
          <div key={`${e.ts}${i}`} className="flex justify-between px-3 py-1">
            <span className="text-zinc-400">{fmtTime(e.ts)}</span>
            <span className="font-medium">{e.symbol}</span>
            <span
              className={e.is_buyer_maker ? 'text-red-400' : 'text-emerald-400'}
            >
              {e.is_buyer_maker ? 'sell' : 'buy'}
            </span>
            <span className="tabular-nums text-zinc-300">
              ${fmtUsd(e.value)}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
