import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import Plot from './Plot'
import { useTopic } from '../ws/hooks'

interface MarksMsg {
  marks: { symbol: string; mark: number; index: number }[]
}

function Basis({ symbol }: { symbol: string }) {
  const [basis, setBasis] = useState<number | null>(null)
  useTopic('marks', (data) => {
    const msg = data as MarksMsg
    const m = msg.marks.find((x) => x.symbol === symbol)
    if (m && m.index > 0) setBasis(((m.mark - m.index) / m.index) * 10_000)
  })
  return (
    <div className="rounded border border-zinc-800 p-3 text-sm">
      <div className="text-xs text-zinc-500">Basis (mark vs index)</div>
      <div
        className={`font-medium tabular-nums ${basis != null && basis >= 0 ? 'text-emerald-400' : 'text-red-400'}`}
      >
        {basis != null ? `${basis.toFixed(2)} bps` : 'waiting for marks…'}
      </div>
    </div>
  )
}

export default function FuturesPanel({ symbol }: { symbol: string }) {
  const funding = useQuery({
    queryKey: ['funding', symbol],
    queryFn: () => api.funding(symbol),
  })
  const oi = useQuery({
    queryKey: ['oi', symbol],
    queryFn: () => api.openInterest(symbol),
  })
  const lsr = useQuery({
    queryKey: ['lsr', symbol],
    queryFn: () => api.longShort(symbol),
  })

  return (
    <div className="grid gap-3 lg:grid-cols-3" data-testid="futures-panel">
      <div className="h-56 rounded border border-zinc-800 p-1">
        {funding.data && funding.data.entries.length > 0 ? (
          <Plot
            testId="funding-chart"
            data={[
              {
                type: 'scatter',
                mode: 'lines',
                x: funding.data.entries.map((e) => e.funding_time),
                y: funding.data.entries.map((e) => e.rate * 100),
                name: 'funding %',
                line: { color: '#34d399' },
              },
            ]}
            layout={{ title: { text: 'Funding rate (%)' }, showlegend: false }}
          />
        ) : (
          <p className="p-3 text-xs text-zinc-500">No funding data.</p>
        )}
      </div>
      <div className="h-56 rounded border border-zinc-800 p-1">
        {oi.data && oi.data.entries.length > 0 ? (
          <Plot
            testId="oi-chart"
            data={[
              {
                type: 'scatter',
                mode: 'lines',
                x: oi.data.entries.map((e) => e.ts),
                y: oi.data.entries.map((e) => e.oi),
                name: 'OI',
                line: { color: '#60a5fa' },
              },
            ]}
            layout={{ title: { text: 'Open interest' }, showlegend: false }}
          />
        ) : (
          <p className="p-3 text-xs text-zinc-500">No OI data.</p>
        )}
      </div>
      <div className="grid gap-3">
        <div className="h-40 rounded border border-zinc-800 p-1">
          {lsr.data && lsr.data.entries.length > 0 ? (
            <Plot
              testId="lsr-chart"
              data={[
                {
                  type: 'scatter',
                  mode: 'lines',
                  x: lsr.data.entries.map((e) => e.ts),
                  y: lsr.data.entries.map((e) => e.ratio),
                  name: 'L/S ratio',
                  line: { color: '#f59e0b' },
                },
              ]}
              layout={{
                title: { text: 'Long/short ratio' },
                showlegend: false,
                margin: { t: 30, r: 8, b: 24, l: 40 },
              }}
            />
          ) : (
            <p className="p-3 text-xs text-zinc-500">No long/short data.</p>
          )}
        </div>
        <Basis symbol={symbol} />
      </div>
    </div>
  )
}
