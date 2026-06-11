import { useState } from 'react'
import Sparkline from './Sparkline'
import { useTopic } from '../ws/hooks'

const MAX_POINTS = 120

interface BookMsg {
  symbol: string
  imbalance_5: number | null
  imbalance_10: number | null
  imbalance_20: number | null
  spread_bps: number | null
}

interface CvdMsg {
  symbol: string
  cvd_1m: number
  cvd_5m: number
}

function usePush(): [number[], (v: number) => void] {
  const [values, setValues] = useState<number[]>([])
  const push = (v: number) => {
    setValues((prev) => [...prev.slice(-MAX_POINTS + 1), v])
  }
  return [values, push]
}

export default function MicroPanel({ symbol }: { symbol: string }) {
  const [imb5, pushImb5] = usePush()
  const [imb20, pushImb20] = usePush()
  const [cvd1, pushCvd1] = usePush()
  const [cvd5, pushCvd5] = usePush()
  const [spread, setSpread] = useState<number | null>(null)

  useTopic(`book:${symbol}`, (data) => {
    const msg = data as BookMsg
    if (msg.symbol !== symbol) return
    if (msg.imbalance_5 != null) pushImb5(msg.imbalance_5)
    if (msg.imbalance_20 != null) pushImb20(msg.imbalance_20)
    setSpread(msg.spread_bps)
  })
  useTopic(`cvd:${symbol}`, (data) => {
    const msg = data as CvdMsg
    if (msg.symbol !== symbol) return
    pushCvd1(msg.cvd_1m)
    pushCvd5(msg.cvd_5m)
  })

  const cells: [string, number[], string, number | undefined][] = [
    ['Imbalance (5)', imb5, '#38bdf8', 0],
    ['Imbalance (20)', imb20, '#a78bfa', 0],
    ['CVD 1m', cvd1, '#2dd4bf', 0],
    ['CVD 5m', cvd5, '#f59e0b', 0],
  ]

  return (
    <div
      className="flex flex-wrap items-center gap-4 text-xs"
      data-testid="micro-panel"
    >
      {cells.map(([label, values, color, baseline]) => (
        <div key={label} className="flex items-center gap-2">
          <span className="text-zinc-500">{label}</span>
          <Sparkline
            values={values}
            color={color}
            baseline={baseline}
            testId={`spark-${label}`}
          />
          <span className="w-16 text-right tabular-nums text-zinc-300">
            {values.length ? formatVal(label, values[values.length - 1]) : '—'}
          </span>
        </div>
      ))}
      <div>
        <span className="text-zinc-500">Spread </span>
        <span className="tabular-nums text-zinc-300">
          {spread != null ? `${spread.toFixed(2)} bps` : '—'}
        </span>
      </div>
    </div>
  )
}

function formatVal(label: string, v: number): string {
  if (label.startsWith('CVD')) {
    return Intl.NumberFormat(undefined, {
      notation: 'compact',
      maximumFractionDigits: 1,
    }).format(v)
  }
  return v.toFixed(3)
}
