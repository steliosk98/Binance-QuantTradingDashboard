import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, type SeriesPoint } from '../api/client'
import Plot from '../components/Plot'
import { useMarketStore } from '../stores/market'

const TABS = ['Distribution', 'Volatility', 'Hurst & Z-Score', 'Pairs'] as const
type Tab = (typeof TABS)[number]

function xy(points: SeriesPoint[]): { x: string[]; y: (number | null)[] } {
  return { x: points.map((p) => p[0]), y: points.map((p) => p[1]) }
}

function StateNote({
  isLoading,
  error,
  children,
}: {
  isLoading: boolean
  error: unknown
  children: React.ReactNode
}) {
  if (isLoading)
    return (
      <p className="p-6 text-zinc-400" role="status">
        Computing…
      </p>
    )
  if (error)
    return (
      <p className="p-6 text-red-400" role="alert">
        {String(error)}
      </p>
    )
  return <>{children}</>
}

function DistributionTab({
  symbol,
  interval,
}: {
  symbol: string
  interval: string
}) {
  const q = useQuery({
    queryKey: ['returns', symbol, interval],
    queryFn: () => api.returnsStats(symbol, interval),
  })
  const d = q.data
  return (
    <StateNote isLoading={q.isLoading} error={q.error}>
      {d && (
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="h-80 rounded border border-zinc-800 p-2">
            <Plot
              testId="dist-histogram"
              data={[
                {
                  type: 'bar',
                  x: d.histogram.edges.slice(0, -1),
                  y: d.histogram.counts,
                  marker: { color: '#34d399' },
                  name: 'returns',
                },
              ]}
              layout={{
                title: {
                  text: `${symbol} ${interval} log-return distribution`,
                },
              }}
            />
          </div>
          <div className="h-80 rounded border border-zinc-800 p-2">
            <Plot
              testId="qq-plot"
              data={[
                {
                  type: 'scattergl',
                  mode: 'markers',
                  x: d.qq.theoretical,
                  y: d.qq.sample,
                  marker: { size: 3, color: '#60a5fa' },
                  name: 'QQ',
                },
                {
                  type: 'scatter',
                  mode: 'lines',
                  x: d.qq.theoretical,
                  y: d.qq.theoretical.map((t) => d.mean + d.std * t),
                  line: { color: '#f87171', width: 1 },
                  name: 'normal',
                },
              ]}
              layout={{ title: { text: 'QQ plot vs normal' } }}
            />
          </div>
          <div className="col-span-full grid grid-cols-2 gap-3 text-sm md:grid-cols-5">
            {[
              ['Samples', d.count.toLocaleString()],
              ['Std', d.std.toExponential(2)],
              ['Skew', d.skew.toFixed(3)],
              ['Excess kurtosis', d.kurtosis.toFixed(2)],
              ['Jarque-Bera p', d.jarque_bera_p.toExponential(2)],
            ].map(([label, value]) => (
              <div key={label} className="rounded border border-zinc-800 p-3">
                <div className="text-xs text-zinc-500">{label}</div>
                <div className="font-medium tabular-nums">{value}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </StateNote>
  )
}

function VolatilityTab({
  symbol,
  interval,
}: {
  symbol: string
  interval: string
}) {
  const q = useQuery({
    queryKey: ['volatility', symbol, interval],
    queryFn: () => api.volatility(symbol, interval),
  })
  const d = q.data
  return (
    <StateNote isLoading={q.isLoading} error={q.error}>
      {d && (
        <div className="h-96 rounded border border-zinc-800 p-2">
          <Plot
            testId="vol-chart"
            data={[
              {
                type: 'scattergl',
                mode: 'lines',
                ...xy(d.close_to_close),
                name: 'close-to-close',
                line: { color: '#34d399' },
              },
              {
                type: 'scattergl',
                mode: 'lines',
                ...xy(d.parkinson),
                name: 'Parkinson',
                line: { color: '#60a5fa' },
              },
              {
                type: 'scattergl',
                mode: 'lines',
                ...xy(d.garman_klass),
                name: 'Garman-Klass',
                line: { color: '#f59e0b' },
              },
            ]}
            layout={{
              title: {
                text: `${symbol} annualized realized volatility (3 estimators)`,
              },
            }}
          />
        </div>
      )}
    </StateNote>
  )
}

function HurstTab({ symbol, interval }: { symbol: string; interval: string }) {
  const q = useQuery({
    queryKey: ['hurst', symbol, interval],
    queryFn: () => api.hurst(symbol, interval),
  })
  const d = q.data
  return (
    <StateNote isLoading={q.isLoading} error={q.error}>
      {d && (
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="h-80 rounded border border-zinc-800 p-2">
            <Plot
              testId="hurst-chart"
              data={[
                {
                  type: 'scatter',
                  mode: 'lines+markers',
                  ...xy(d.rolling),
                  name: 'rolling Hurst',
                  line: { color: '#a78bfa' },
                },
              ]}
              layout={{
                title: {
                  text: `Hurst exponent (overall: ${d.hurst?.toFixed(3) ?? 'n/a'}) — >0.55 trending, <0.45 mean-reverting`,
                },
                shapes: [
                  {
                    type: 'line',
                    xref: 'paper',
                    x0: 0,
                    x1: 1,
                    y0: 0.5,
                    y1: 0.5,
                    line: { color: '#52525b', dash: 'dot' },
                  },
                ],
              }}
            />
          </div>
          <div className="h-80 rounded border border-zinc-800 p-2">
            <Plot
              testId="zscore-chart"
              data={[
                {
                  type: 'scattergl',
                  mode: 'lines',
                  ...xy(d.zscore),
                  name: 'price z-score',
                  line: { color: '#34d399' },
                },
              ]}
              layout={{
                title: { text: 'Price z-score vs 50-bar rolling mean' },
              }}
            />
          </div>
        </div>
      )}
    </StateNote>
  )
}

function PairsTab({
  symbols,
  interval,
}: {
  symbols: string[]
  interval: string
}) {
  const [a, setA] = useState('BTCUSDT')
  const [b, setB] = useState('ETHUSDT')
  const q = useQuery({
    queryKey: ['pairs', a, b, interval],
    queryFn: () => api.pairs(a, b, interval),
    enabled: a !== b,
  })
  const d = q.data
  return (
    <div>
      <div className="mb-4 flex items-center gap-3">
        {[
          [a, setA],
          [b, setB],
        ].map(([val, set], i) => (
          <select
            key={i}
            aria-label={i === 0 ? 'Symbol A' : 'Symbol B'}
            value={val as string}
            onChange={(e) => (set as (v: string) => void)(e.target.value)}
            className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-sm"
          >
            {symbols.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        ))}
        {a === b && (
          <span className="text-sm text-amber-400">
            Pick two different symbols
          </span>
        )}
      </div>
      <StateNote isLoading={q.isLoading} error={q.error}>
        {d && (
          <div className="grid gap-4">
            <div className="flex gap-3 text-sm">
              <div className="rounded border border-zinc-800 p-3">
                <div className="text-xs text-zinc-500">
                  Engle-Granger p-value
                </div>
                <div
                  className={`font-medium ${d.cointegrated_5pct ? 'text-emerald-400' : 'text-red-400'}`}
                >
                  {d.pvalue.toFixed(4)}{' '}
                  {d.cointegrated_5pct
                    ? '(cointegrated @5%)'
                    : '(not cointegrated)'}
                </div>
              </div>
              <div className="rounded border border-zinc-800 p-3">
                <div className="text-xs text-zinc-500">Hedge ratio</div>
                <div className="font-medium tabular-nums">
                  {d.hedge_ratio.toFixed(4)}
                </div>
              </div>
            </div>
            <div className="h-80 rounded border border-zinc-800 p-2">
              <Plot
                testId="spread-z-chart"
                data={[
                  {
                    type: 'scattergl',
                    mode: 'lines',
                    ...xy(d.spread_z),
                    name: 'spread z-score',
                    line: { color: '#34d399' },
                  },
                ]}
                layout={{ title: { text: `${a} / ${b} spread z-score` } }}
              />
            </div>
          </div>
        )}
      </StateNote>
    </div>
  )
}

export default function ResearchPage() {
  const { symbol, interval } = useMarketStore()
  const [tab, setTab] = useState<Tab>('Distribution')
  const symbolsQuery = useQuery({ queryKey: ['symbols'], queryFn: api.symbols })
  const symbols = symbolsQuery.data?.watchlist ?? ['BTCUSDT', 'ETHUSDT']

  return (
    <div>
      <div className="mb-4 flex items-center gap-4">
        <h1 className="text-2xl font-semibold">Research</h1>
        <SymbolPicker />
        <div className="flex gap-1">
          {TABS.map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`rounded px-3 py-1 text-sm ${
                t === tab
                  ? 'bg-emerald-600 text-white'
                  : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700'
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      </div>
      {tab === 'Distribution' && (
        <DistributionTab symbol={symbol} interval={interval} />
      )}
      {tab === 'Volatility' && (
        <VolatilityTab symbol={symbol} interval={interval} />
      )}
      {tab === 'Hurst & Z-Score' && (
        <HurstTab symbol={symbol} interval={interval} />
      )}
      {tab === 'Pairs' && <PairsTab symbols={symbols} interval={interval} />}
    </div>
  )
}

function SymbolPicker() {
  const { symbol, setSymbol } = useMarketStore()
  const symbolsQuery = useQuery({ queryKey: ['symbols'], queryFn: api.symbols })
  const symbols = symbolsQuery.data?.watchlist ?? ['BTCUSDT']
  return (
    <select
      aria-label="Symbol"
      value={symbol}
      onChange={(e) => setSymbol(e.target.value)}
      className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-sm"
    >
      {symbols.map((s) => (
        <option key={s}>{s}</option>
      ))}
    </select>
  )
}
