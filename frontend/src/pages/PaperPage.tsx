import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  api,
  type PaperInstanceDetail,
  type PaperInstanceSummary,
} from '../api/client'
import Plot from '../components/Plot'

function InstanceForm({ onCreated }: { onCreated: () => void }) {
  const strategiesQuery = useQuery({
    queryKey: ['strategies'],
    queryFn: api.strategies,
  })
  const symbolsQuery = useQuery({ queryKey: ['symbols'], queryFn: api.symbols })
  const [name, setName] = useState('my-strategy')
  const [strategyKey, setStrategyKey] = useState('zscore_mr')
  const [symbol, setSymbol] = useState('BTCUSDT')
  const [interval, setInterval] = useState('1m')
  const [qtyUsd, setQtyUsd] = useState(1000)
  const [maxPos, setMaxPos] = useState(2000)
  const [maxLoss, setMaxLoss] = useState(500)
  const [params, setParams] = useState<Record<string, number>>({})
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const spec = strategiesQuery.data?.strategies.find(
    (s) => s.key === strategyKey,
  )

  const create = async () => {
    if (!spec) return
    setBusy(true)
    setError(null)
    try {
      await api.createPaperInstance({
        name,
        strategy: strategyKey,
        symbol,
        interval,
        qty_usd: qtyUsd,
        params: Object.fromEntries(
          spec.params.map((p) => [p.name, params[p.name] ?? p.default]),
        ),
        max_position_usd: maxPos,
        max_daily_loss_usd: maxLoss,
      })
      onCreated()
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-wrap items-end gap-3 rounded border border-zinc-800 p-3">
      <label className="text-sm">
        <div className="text-xs text-zinc-500">Name</div>
        <input
          aria-label="Instance name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-36 rounded-sm border border-zinc-700 bg-zinc-950/60 px-2 py-1 font-mono text-sm"
        />
      </label>
      <label className="text-sm">
        <div className="text-xs text-zinc-500">Strategy</div>
        <select
          value={strategyKey}
          onChange={(e) => {
            setStrategyKey(e.target.value)
            setParams({})
          }}
          className="rounded-sm border border-zinc-700 bg-zinc-950/60 px-2 py-1 font-mono text-sm"
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
          className="rounded-sm border border-zinc-700 bg-zinc-950/60 px-2 py-1 font-mono text-sm"
        >
          {(symbolsQuery.data?.watchlist ?? ['BTCUSDT']).map((s) => (
            <option key={s}>{s}</option>
          ))}
        </select>
      </label>
      <label className="text-sm">
        <div className="text-xs text-zinc-500">Interval</div>
        <select
          value={interval}
          onChange={(e) => setInterval(e.target.value)}
          className="rounded-sm border border-zinc-700 bg-zinc-950/60 px-2 py-1 font-mono text-sm"
        >
          {['1m', '5m', '15m', '1h'].map((iv) => (
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
            className="w-24 rounded-sm border border-zinc-700 bg-zinc-950/60 px-2 py-1 font-mono text-sm"
          />
        </label>
      ))}
      <label className="text-sm">
        <div className="text-xs text-zinc-500">Size (USD)</div>
        <input
          type="number"
          aria-label="Size USD"
          value={qtyUsd}
          onChange={(e) => setQtyUsd(Number(e.target.value))}
          className="w-24 rounded-sm border border-zinc-700 bg-zinc-950/60 px-2 py-1 font-mono text-sm"
        />
      </label>
      <label className="text-sm">
        <div className="text-xs text-zinc-500">Max position (USD)</div>
        <input
          type="number"
          aria-label="Max position USD"
          value={maxPos}
          onChange={(e) => setMaxPos(Number(e.target.value))}
          className="w-24 rounded-sm border border-zinc-700 bg-zinc-950/60 px-2 py-1 font-mono text-sm"
        />
      </label>
      <label className="text-sm">
        <div className="text-xs text-zinc-500">Max daily loss (USD)</div>
        <input
          type="number"
          aria-label="Max daily loss USD"
          value={maxLoss}
          onChange={(e) => setMaxLoss(Number(e.target.value))}
          className="w-24 rounded-sm border border-zinc-700 bg-zinc-950/60 px-2 py-1 font-mono text-sm"
        />
      </label>
      <button
        onClick={() => void create()}
        disabled={busy}
        className="rounded bg-amber-500 px-4 py-1.5 text-sm font-semibold text-zinc-950 hover:bg-amber-400 disabled:opacity-50"
      >
        Create instance
      </button>
      {error && (
        <span className="text-xs text-red-400" role="alert">
          {error}
        </span>
      )}
    </div>
  )
}

function InstanceRow({
  inst,
  selected,
  onSelect,
  onToggle,
}: {
  inst: PaperInstanceSummary
  selected: boolean
  onSelect: () => void
  onToggle: () => void
}) {
  return (
    <tr
      className={`cursor-pointer border-t border-zinc-800/60 hover:bg-zinc-800/40 ${selected ? 'bg-zinc-800/60' : ''}`}
      onClick={onSelect}
    >
      <td className="px-2 py-1.5 font-medium">{inst.name}</td>
      <td className="px-2 py-1.5">{inst.strategy}</td>
      <td className="px-2 py-1.5">
        {inst.symbol} {inst.interval}
      </td>
      <td className="px-2 py-1.5">
        <span
          className={
            inst.status === 'running' ? 'text-emerald-400' : 'text-zinc-500'
          }
        >
          {inst.status}
        </span>
        {inst.halted_today && (
          <span className="ml-1 text-amber-400">(halted: daily loss)</span>
        )}
      </td>
      <td className="px-2 py-1.5 text-right tabular-nums">
        {inst.position_qty.toFixed(6)}
      </td>
      <td
        className={`px-2 py-1.5 text-right tabular-nums ${inst.realized_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}
      >
        ${inst.realized_pnl.toFixed(2)}
      </td>
      <td className="px-2 py-1.5">
        <button
          onClick={(e) => {
            e.stopPropagation()
            onToggle()
          }}
          className={`rounded px-2 py-0.5 text-xs font-medium ${
            inst.status === 'running'
              ? 'bg-red-600 text-white hover:bg-red-500'
              : 'bg-emerald-600 text-white hover:bg-emerald-500'
          }`}
        >
          {inst.status === 'running' ? 'Kill switch' : 'Start'}
        </button>
      </td>
    </tr>
  )
}

function InstanceDetail({ detail }: { detail: PaperInstanceDetail }) {
  return (
    <div className="grid gap-3">
      {detail.equity.length > 1 ? (
        <div className="h-64 rounded border border-zinc-800 p-1">
          <Plot
            testId="paper-equity-chart"
            data={[
              {
                type: 'scattergl',
                mode: 'lines',
                x: detail.equity.map((e) => e[0]),
                y: detail.equity.map((e) => e[1]),
                name: 'equity (USD)',
                line: { color: '#2dd4bf' },
              },
            ]}
            layout={{ title: { text: `${detail.name} — paper equity` } }}
          />
        </div>
      ) : (
        <p className="text-sm text-zinc-500">Waiting for equity history…</p>
      )}
      <div className="max-h-64 overflow-auto rounded border border-zinc-800">
        <table className="w-full text-xs" data-testid="paper-orders">
          <thead className="sticky top-0 bg-zinc-900 text-left uppercase text-zinc-500">
            <tr>
              <th className="px-2 py-1">Time</th>
              <th className="px-2 py-1">Side</th>
              <th className="px-2 py-1 text-right">Qty</th>
              <th className="px-2 py-1 text-right">Price</th>
              <th className="px-2 py-1">Signal</th>
              <th className="px-2 py-1">Testnet ID</th>
            </tr>
          </thead>
          <tbody>
            {detail.orders.length === 0 && (
              <tr>
                <td colSpan={6} className="px-2 py-3 text-zinc-500">
                  No orders yet — waiting for signals.
                </td>
              </tr>
            )}
            {detail.orders.map((o) => (
              <tr key={o.id} className="border-t border-zinc-800/60">
                <td className="px-2 py-1">{o.ts.slice(0, 19)}</td>
                <td
                  className={`px-2 py-1 ${o.side === 'BUY' ? 'text-emerald-400' : 'text-red-400'}`}
                >
                  {o.side}
                </td>
                <td className="px-2 py-1 text-right tabular-nums">
                  {o.qty.toFixed(6)}
                </td>
                <td className="px-2 py-1 text-right tabular-nums">
                  {o.price.toFixed(2)}
                </td>
                <td className="px-2 py-1 text-zinc-400">{o.signal}</td>
                <td className="px-2 py-1 text-zinc-500">
                  {o.testnet_order_id ?? 'sim'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default function PaperPage() {
  const queryClient = useQueryClient()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const instancesQuery = useQuery({
    queryKey: ['paper-instances'],
    queryFn: api.paperInstances,
    refetchInterval: 5000,
  })
  const detailQuery = useQuery({
    queryKey: ['paper-instance', selectedId],
    queryFn: () => api.paperInstance(selectedId!),
    enabled: selectedId != null,
    refetchInterval: 5000,
  })

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ['paper-instances'] })
    void queryClient.invalidateQueries({ queryKey: ['paper-instance'] })
  }

  const toggle = async (inst: PaperInstanceSummary) => {
    if (inst.status === 'running') await api.stopPaperInstance(inst.id)
    else await api.startPaperInstance(inst.id)
    refresh()
  }

  return (
    <div className="grid gap-4">
      <h1 className="text-2xl font-semibold">Paper Trading</h1>
      <p className="text-xs text-zinc-500">
        Orders go to Binance Spot Testnet when testnet keys are configured;
        otherwise fills are simulated internally. No live trading exists.
      </p>
      <InstanceForm onCreated={refresh} />
      {instancesQuery.isLoading && (
        <p className="text-zinc-400" role="status">
          Loading instances…
        </p>
      )}
      {instancesQuery.isError && (
        <p className="text-red-400" role="alert">
          {String(instancesQuery.error)}
        </p>
      )}
      <div className="overflow-x-auto rounded border border-zinc-800">
        <table className="w-full text-sm" data-testid="paper-instances">
          <thead className="bg-zinc-900 text-left text-xs uppercase text-zinc-500">
            <tr>
              <th className="px-2 py-2">Name</th>
              <th className="px-2 py-2">Strategy</th>
              <th className="px-2 py-2">Market</th>
              <th className="px-2 py-2">Status</th>
              <th className="px-2 py-2 text-right">Position</th>
              <th className="px-2 py-2 text-right">Realized PnL</th>
              <th className="px-2 py-2">Control</th>
            </tr>
          </thead>
          <tbody>
            {(instancesQuery.data?.instances ?? []).map((inst) => (
              <InstanceRow
                key={inst.id}
                inst={inst}
                selected={inst.id === selectedId}
                onSelect={() => setSelectedId(inst.id)}
                onToggle={() => void toggle(inst)}
              />
            ))}
          </tbody>
        </table>
      </div>
      {detailQuery.data && <InstanceDetail detail={detailQuery.data} />}
    </div>
  )
}
