import { useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  api,
  type BacktestDetail,
  type BacktestMetrics,
  type StrategySpec,
} from '../api/client'
import Plot from '../components/Plot'

const METRIC_CARDS: [keyof BacktestMetrics, string, (v: number) => string][] = [
  ['total_return', 'Total return', (v) => `${(v * 100).toFixed(2)}%`],
  ['annualized_return', 'Annualized', (v) => `${(v * 100).toFixed(2)}%`],
  ['sharpe', 'Sharpe', (v) => v.toFixed(2)],
  ['sortino', 'Sortino', (v) => v.toFixed(2)],
  ['calmar', 'Calmar', (v) => v.toFixed(2)],
  ['max_drawdown', 'Max DD', (v) => `${(v * 100).toFixed(2)}%`],
  ['win_rate', 'Win rate', (v) => `${(v * 100).toFixed(1)}%`],
  ['profit_factor', 'Profit factor', (v) => v.toFixed(2)],
  ['exposure', 'Exposure', (v) => `${(v * 100).toFixed(1)}%`],
  ['n_trades', 'Trades', (v) => String(v)],
]

function MetricsCards({ metrics }: { metrics: BacktestMetrics }) {
  return (
    <div
      className="grid grid-cols-2 gap-2 sm:grid-cols-5"
      data-testid="metrics-cards"
    >
      {METRIC_CARDS.map(([key, label, fmt]) => {
        const v = metrics[key]
        return (
          <div key={key} className="rounded border border-zinc-800 p-2">
            <div className="text-xs text-zinc-500">{label}</div>
            <div className="text-sm font-medium tabular-nums">
              {v == null ? '—' : fmt(v as number)}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function monthlyReturns(equity: [string, number, number][]): {
  years: string[]
  months: string[]
  z: (number | null)[][]
} {
  const byMonth = new Map<string, { first: number; last: number }>()
  for (const [t, e] of equity) {
    const key = t.slice(0, 7)
    const entry = byMonth.get(key)
    if (!entry) byMonth.set(key, { first: e, last: e })
    else entry.last = e
  }
  const keys = [...byMonth.keys()].sort()
  const years = [...new Set(keys.map((k) => k.slice(0, 4)))]
  const months = [
    '01',
    '02',
    '03',
    '04',
    '05',
    '06',
    '07',
    '08',
    '09',
    '10',
    '11',
    '12',
  ]
  let prevLast: number | null = null
  const returns = new Map<string, number>()
  for (const k of keys) {
    const m = byMonth.get(k)!
    const base = prevLast ?? m.first
    returns.set(k, m.last / base - 1)
    prevLast = m.last
  }
  const z = years.map((y) =>
    months.map((m) => {
      const r = returns.get(`${y}-${m}`)
      return r == null ? null : r * 100
    }),
  )
  return { years, months, z }
}

function EquityChart({ detail }: { detail: BacktestDetail }) {
  const equity = detail.equity ?? []
  const x = equity.map((p) => p[0])
  return (
    <div className="h-96 rounded border border-zinc-800 p-1">
      <Plot
        testId="equity-chart"
        data={[
          {
            type: 'scattergl',
            mode: 'lines',
            x,
            y: equity.map((p) => p[1]),
            name: 'equity',
            line: { color: '#34d399' },
          },
          {
            type: 'scattergl',
            mode: 'lines',
            x,
            y: equity.map((p) => p[2] * 100),
            name: 'drawdown %',
            yaxis: 'y2',
            fill: 'tozeroy',
            line: { color: '#f87171', width: 1 },
            fillcolor: 'rgba(248,113,113,0.15)',
          },
        ]}
        layout={{
          title: {
            text: `${detail.symbol} ${detail.interval} — ${detail.strategy}`,
          },
          yaxis: { title: { text: 'equity' } },
          yaxis2: {
            overlaying: 'y',
            side: 'right',
            title: { text: 'DD %' },
            gridcolor: 'transparent',
          },
        }}
      />
    </div>
  )
}

function MonthlyHeatmap({ equity }: { equity: [string, number, number][] }) {
  const { years, months, z } = useMemo(() => monthlyReturns(equity), [equity])
  return (
    <div className="h-64 rounded border border-zinc-800 p-1">
      <Plot
        testId="monthly-heatmap"
        data={[
          {
            type: 'heatmap',
            x: months,
            y: years,
            z,
            colorscale: 'RdBu',
            reversescale: false,
          },
        ]}
        layout={{
          title: { text: 'Monthly returns (%)' },
          showlegend: false,
          margin: { t: 36, r: 10, b: 30, l: 60 },
        }}
      />
    </div>
  )
}

function WalkForwardView({ detail }: { detail: BacktestDetail }) {
  const wf = detail.walk_forward
  if (!wf) return null
  return (
    <div className="grid gap-3" data-testid="walkforward-view">
      <div className="h-72 rounded border border-zinc-800 p-1">
        <Plot
          testId="oos-equity-chart"
          data={[
            {
              type: 'scattergl',
              mode: 'lines',
              x: wf.oos_equity.map((p) => p[0]),
              y: wf.oos_equity.map((p) => p[1]),
              name: 'OOS equity',
              line: { color: '#a78bfa' },
            },
          ]}
          layout={{ title: { text: 'Out-of-sample stitched equity' } }}
        />
      </div>
      <div className="overflow-x-auto rounded border border-zinc-800">
        <table className="w-full text-xs">
          <thead className="bg-zinc-900 text-left uppercase text-zinc-500">
            <tr>
              <th className="px-2 py-1">Window</th>
              <th className="px-2 py-1">Best params</th>
              <th className="px-2 py-1 text-right">IS Sharpe</th>
              <th className="px-2 py-1 text-right">OOS Sharpe</th>
              <th className="px-2 py-1 text-right">IS return</th>
              <th className="px-2 py-1 text-right">OOS return</th>
            </tr>
          </thead>
          <tbody>
            {wf.windows.map((w, i) => (
              <tr key={i} className="border-t border-zinc-800/60">
                <td className="px-2 py-1">{i + 1}</td>
                <td className="px-2 py-1 font-mono">
                  {Object.entries(w.best_params)
                    .map(([k, v]) => `${k}=${v}`)
                    .join(' ')}
                </td>
                <td className="px-2 py-1 text-right tabular-nums">
                  {w.in_sample.sharpe?.toFixed(2) ?? '—'}
                </td>
                <td className="px-2 py-1 text-right tabular-nums">
                  {w.out_of_sample.sharpe?.toFixed(2) ?? '—'}
                </td>
                <td className="px-2 py-1 text-right tabular-nums">
                  {(w.in_sample.total_return * 100).toFixed(1)}%
                </td>
                <td className="px-2 py-1 text-right tabular-nums">
                  {(w.out_of_sample.total_return * 100).toFixed(1)}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function TradesTable({ detail }: { detail: BacktestDetail }) {
  const trades = detail.trades ?? []
  return (
    <div className="max-h-72 overflow-auto rounded border border-zinc-800">
      <table className="w-full text-xs" data-testid="trades-table">
        <thead className="sticky top-0 bg-zinc-900 text-left uppercase text-zinc-500">
          <tr>
            <th className="px-2 py-1">Entry</th>
            <th className="px-2 py-1">Exit</th>
            <th className="px-2 py-1">Dir</th>
            <th className="px-2 py-1 text-right">Entry px</th>
            <th className="px-2 py-1 text-right">Exit px</th>
            <th className="px-2 py-1 text-right">PnL %</th>
            <th className="px-2 py-1 text-right">Bars</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t, i) => (
            <tr key={i} className="border-t border-zinc-800/60">
              <td className="px-2 py-1">{t.entry_time.slice(0, 16)}</td>
              <td className="px-2 py-1">{t.exit_time.slice(0, 16)}</td>
              <td
                className={`px-2 py-1 ${t.direction === 'long' ? 'text-emerald-400' : 'text-red-400'}`}
              >
                {t.direction}
              </td>
              <td className="px-2 py-1 text-right tabular-nums">
                {t.entry_price.toFixed(2)}
              </td>
              <td className="px-2 py-1 text-right tabular-nums">
                {t.exit_price.toFixed(2)}
              </td>
              <td
                className={`px-2 py-1 text-right tabular-nums ${t.pnl_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}`}
              >
                {(t.pnl_pct * 100).toFixed(2)}%
              </td>
              <td className="px-2 py-1 text-right tabular-nums">{t.bars}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function CompareChart({ details }: { details: BacktestDetail[] }) {
  const colors = ['#34d399', '#60a5fa', '#f59e0b']
  return (
    <div className="h-80 rounded border border-zinc-800 p-1">
      <Plot
        testId="compare-chart"
        data={details.map((d, i) => ({
          type: 'scattergl' as const,
          mode: 'lines' as const,
          x: (d.equity ?? []).map((p) => p[0]),
          y: (d.equity ?? []).map((p) => p[1]),
          name: `${d.strategy} ${d.symbol}`,
          line: { color: colors[i % colors.length] },
        }))}
        layout={{ title: { text: 'Equity comparison' } }}
      />
    </div>
  )
}

export default function BacktestPage() {
  const queryClient = useQueryClient()
  const strategiesQuery = useQuery({
    queryKey: ['strategies'],
    queryFn: api.strategies,
  })
  const symbolsQuery = useQuery({ queryKey: ['symbols'], queryFn: api.symbols })
  const savedQuery = useQuery({
    queryKey: ['backtests'],
    queryFn: api.listBacktests,
  })

  const [strategyKey, setStrategyKey] = useState('sma_crossover')
  const [symbol, setSymbol] = useState('BTCUSDT')
  const [interval, setInterval] = useState('1h')
  const [params, setParams] = useState<Record<string, number>>({})
  const [walkForward, setWalkForward] = useState(false)
  const [runId, setRunId] = useState<string | null>(null)
  const [compareIds, setCompareIds] = useState<string[]>([])
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  const spec: StrategySpec | undefined = strategiesQuery.data?.strategies.find(
    (s) => s.key === strategyKey,
  )

  const resultQuery = useQuery({
    queryKey: ['backtest', runId],
    queryFn: () => api.getBacktest(runId!),
    enabled: runId != null,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'done' || status === 'error' ? false : 700
    },
  })

  const compareQueries = useQuery({
    queryKey: ['backtest-compare', compareIds],
    queryFn: () => Promise.all(compareIds.map((id) => api.getBacktest(id))),
    enabled: compareIds.length >= 2,
  })

  const run = async () => {
    if (!spec) return
    setSubmitting(true)
    setSubmitError(null)
    try {
      const fullParams = Object.fromEntries(
        spec.params.map((p) => [p.name, params[p.name] ?? p.default]),
      )
      const { id } = await api.createBacktest({
        strategy: spec.key,
        symbol,
        interval,
        params: fullParams,
        walk_forward: walkForward,
      })
      setRunId(id)
      void queryClient.invalidateQueries({ queryKey: ['backtests'] })
    } catch (e) {
      setSubmitError(String(e))
    } finally {
      setSubmitting(false)
    }
  }

  const detail = resultQuery.data
  const symbols = symbolsQuery.data?.watchlist ?? ['BTCUSDT']

  return (
    <div className="grid gap-4">
      <h1 className="text-2xl font-semibold">Backtest</h1>

      <div className="flex flex-wrap items-end gap-3 rounded border border-zinc-800 p-3">
        <label className="text-sm">
          <div className="text-xs text-zinc-500">Strategy</div>
          <select
            value={strategyKey}
            onChange={(e) => {
              setStrategyKey(e.target.value)
              setParams({})
            }}
            className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1"
          >
            {strategiesQuery.data?.strategies.map((s) => (
              <option key={s.key} value={s.key}>
                {s.name}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          <div className="text-xs text-zinc-500">Symbol</div>
          <select
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1"
          >
            {symbols.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          <div className="text-xs text-zinc-500">Interval</div>
          <select
            value={interval}
            onChange={(e) => setInterval(e.target.value)}
            className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1"
          >
            {['1m', '5m', '15m', '1h', '4h', '1d'].map((iv) => (
              <option key={iv}>{iv}</option>
            ))}
          </select>
        </label>
        {spec?.params.map((p) => (
          <label key={p.name} className="text-sm">
            <div className="text-xs text-zinc-500">{p.label}</div>
            <input
              type="number"
              aria-label={p.label}
              value={params[p.name] ?? p.default}
              min={p.min}
              max={p.max}
              step={p.step}
              onChange={(e) =>
                setParams((prev) => ({
                  ...prev,
                  [p.name]: Number(e.target.value),
                }))
              }
              className="w-24 rounded border border-zinc-700 bg-zinc-900 px-2 py-1"
            />
          </label>
        ))}
        <label className="flex items-center gap-1 text-sm text-zinc-400">
          <input
            type="checkbox"
            checked={walkForward}
            onChange={(e) => setWalkForward(e.target.checked)}
          />
          Walk-forward
        </label>
        <button
          onClick={() => void run()}
          disabled={submitting || !spec}
          className="rounded bg-emerald-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
        >
          {submitting ? 'Submitting…' : 'Run backtest'}
        </button>
        {spec && (
          <span className="text-xs text-zinc-500">{spec.description}</span>
        )}
        {submitError && (
          <span className="text-xs text-red-400" role="alert">
            {submitError}
          </span>
        )}
      </div>

      {runId &&
        detail &&
        detail.status !== 'done' &&
        detail.status !== 'error' && (
          <p className="text-zinc-400" role="status">
            Running backtest… ({detail.status})
          </p>
        )}
      {detail?.status === 'error' && (
        <p className="text-red-400" role="alert">
          Backtest failed: {detail.error}
        </p>
      )}
      {detail?.status === 'done' && detail.metrics && (
        <>
          <MetricsCards metrics={detail.metrics} />
          <EquityChart detail={detail} />
          {detail.equity && <MonthlyHeatmap equity={detail.equity} />}
          {detail.walk_forward && <WalkForwardView detail={detail} />}
          <TradesTable detail={detail} />
        </>
      )}

      <div className="rounded border border-zinc-800">
        <div className="border-b border-zinc-800 px-3 py-2 text-sm font-medium">
          Saved backtests{' '}
          {compareIds.length >= 2 ? '' : '(select 2–3 to compare)'}
        </div>
        <div className="max-h-64 overflow-y-auto">
          <table className="w-full text-xs" data-testid="saved-backtests">
            <tbody>
              {(savedQuery.data?.backtests ?? []).map((b) => (
                <tr
                  key={b.id}
                  className="border-t border-zinc-800/60 hover:bg-zinc-800/40"
                >
                  <td className="px-2 py-1">
                    <input
                      type="checkbox"
                      aria-label={`compare ${b.id}`}
                      checked={compareIds.includes(b.id)}
                      disabled={
                        b.status !== 'done' ||
                        (compareIds.length >= 3 && !compareIds.includes(b.id))
                      }
                      onChange={(e) =>
                        setCompareIds((prev) =>
                          e.target.checked
                            ? [...prev, b.id]
                            : prev.filter((x) => x !== b.id),
                        )
                      }
                    />
                  </td>
                  <td className="px-2 py-1">{b.created_at.slice(0, 16)}</td>
                  <td className="px-2 py-1 font-medium">{b.strategy}</td>
                  <td className="px-2 py-1">
                    {b.symbol} {b.interval}
                  </td>
                  <td className="px-2 py-1">{b.status}</td>
                  <td className="px-2 py-1 text-right tabular-nums">
                    {b.metrics
                      ? `${(b.metrics.total_return * 100).toFixed(1)}%`
                      : '—'}
                  </td>
                  <td className="px-2 py-1 text-right tabular-nums">
                    Sharpe {b.metrics?.sharpe?.toFixed(2) ?? '—'}
                  </td>
                  <td className="px-2 py-1">
                    <button
                      onClick={() => setRunId(b.id)}
                      className="text-emerald-400 hover:underline"
                    >
                      load
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      {compareQueries.data && compareQueries.data.length >= 2 && (
        <CompareChart details={compareQueries.data} />
      )}
    </div>
  )
}
