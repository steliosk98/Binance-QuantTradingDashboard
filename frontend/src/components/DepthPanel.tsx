import { useState } from 'react'
import { useTopic } from '../ws/hooks'

interface BookData {
  symbol: string
  bids: [number, number][]
  asks: [number, number][]
}

function cumulative(
  levels: [number, number][],
): { price: number; qty: number; cum: number }[] {
  let cum = 0
  return levels.map(([price, qty]) => {
    cum += qty
    return { price, qty, cum }
  })
}

export default function DepthPanel({ symbol }: { symbol: string }) {
  const [book, setBook] = useState<BookData | null>(null)
  useTopic(`book:${symbol}`, (data) => setBook(data as BookData))

  if (!book || book.symbol !== symbol) {
    return (
      <div className="p-3 text-xs text-zinc-500">
        Order book unavailable for {symbol} (books are maintained for BTCUSDT
        and ETHUSDT).
      </div>
    )
  }

  const bids = cumulative(book.bids)
  const asks = cumulative(book.asks)
  const maxCum = Math.max(bids.at(-1)?.cum ?? 0, asks.at(-1)?.cum ?? 0, 1e-9)
  const mid =
    book.bids.length && book.asks.length
      ? (book.bids[0][0] + book.asks[0][0]) / 2
      : null
  const spreadBps =
    book.bids.length && book.asks.length && mid
      ? ((book.asks[0][0] - book.bids[0][0]) / mid) * 10_000
      : null

  return (
    <div className="flex h-full flex-col text-xs" data-testid="depth-panel">
      <div className="border-b border-zinc-800 px-3 py-2 text-zinc-400">
        Depth — {symbol}
        {spreadBps != null && (
          <span className="ml-2 text-zinc-500">
            spread {spreadBps.toFixed(2)} bps
          </span>
        )}
      </div>
      <div className="flex-1 overflow-y-auto px-1 py-1">
        {[...asks].reverse().map((a) => (
          <div
            key={`a${a.price}`}
            className="relative flex justify-between px-2 py-0.5"
          >
            <div
              className="absolute inset-y-0 right-0 bg-red-500/15"
              style={{ width: `${(a.cum / maxCum) * 100}%` }}
            />
            <span className="relative text-red-400 tabular-nums">
              {a.price}
            </span>
            <span className="relative text-zinc-400 tabular-nums">
              {a.qty.toFixed(4)}
            </span>
          </div>
        ))}
        {mid != null && (
          <div className="border-y border-zinc-700 px-2 py-1 text-center font-semibold text-zinc-200 tabular-nums">
            {mid.toFixed(2)}
          </div>
        )}
        {bids.map((b) => (
          <div
            key={`b${b.price}`}
            className="relative flex justify-between px-2 py-0.5"
          >
            <div
              className="absolute inset-y-0 right-0 bg-emerald-500/15"
              style={{ width: `${(b.cum / maxCum) * 100}%` }}
            />
            <span className="relative text-emerald-400 tabular-nums">
              {b.price}
            </span>
            <span className="relative text-zinc-400 tabular-nums">
              {b.qty.toFixed(4)}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
