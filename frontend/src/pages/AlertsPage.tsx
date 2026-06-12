import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type AlertRuleOut } from '../api/client'
import Panel from '../components/Panel'

const KINDS = [
  { key: 'price_cross', label: 'Price cross', needsSymbol: true },
  { key: 'whale_trade', label: 'Whale trade', needsSymbol: false },
  { key: 'liquidation', label: 'Liquidation', needsSymbol: false },
  { key: 'funding_abs', label: 'Funding extreme', needsSymbol: false },
  { key: 'regime_change', label: 'Regime change', needsSymbol: true },
] as const

function paramFields(
  kind: string,
): { name: string; label: string; def: number }[] {
  switch (kind) {
    case 'price_cross':
      return [{ name: 'level', label: 'Price level', def: 70000 }]
    case 'whale_trade':
    case 'liquidation':
      return [{ name: 'min_usd', label: 'Min value (USD)', def: 500000 }]
    case 'funding_abs':
      return [
        { name: 'min_abs_rate', label: 'Min |rate| (e.g. 0.001)', def: 0.001 },
      ]
    default:
      return []
  }
}

function describe(rule: AlertRuleOut): string {
  const p = rule.params
  switch (rule.kind) {
    case 'price_cross':
      return `${rule.symbol} ${p.direction ?? 'above'} ${Number(p.level).toLocaleString()}`
    case 'whale_trade':
      return `${rule.symbol ?? 'any'} ≥ $${Number(p.min_usd).toLocaleString()}`
    case 'liquidation':
      return `${rule.symbol ?? 'any'} ≥ $${Number(p.min_usd).toLocaleString()}`
    case 'funding_abs':
      return `|funding| ≥ ${p.min_abs_rate}`
    case 'regime_change':
      return `${rule.symbol} trend label change`
    default:
      return ''
  }
}

export default function AlertsPage() {
  const queryClient = useQueryClient()
  const rulesQuery = useQuery({
    queryKey: ['alert-rules'],
    queryFn: api.alertRules,
  })
  const eventsQuery = useQuery({
    queryKey: ['alert-events'],
    queryFn: () => api.alertEvents(100),
    refetchInterval: 15_000,
  })
  const symbolsQuery = useQuery({ queryKey: ['symbols'], queryFn: api.symbols })

  const [name, setName] = useState('')
  const [kind, setKind] = useState<string>('price_cross')
  const [symbol, setSymbol] = useState('BTCUSDT')
  const [direction, setDirection] = useState<'above' | 'below'>('above')
  const [params, setParams] = useState<Record<string, number>>({})
  const [error, setError] = useState<string | null>(null)

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ['alert-rules'] })
    void queryClient.invalidateQueries({ queryKey: ['alert-events'] })
  }

  const kindSpec = KINDS.find((k) => k.key === kind)!

  const create = async () => {
    setError(null)
    try {
      const fields = paramFields(kind)
      const body: Record<string, number | string> = {}
      for (const f of fields) body[f.name] = params[f.name] ?? f.def
      if (kind === 'price_cross') body.direction = direction
      await api.createAlertRule({
        name:
          name ||
          `${kindSpec.label} ${kindSpec.needsSymbol ? symbol : ''}`.trim(),
        kind,
        symbol: kindSpec.needsSymbol ? symbol : null,
        params: body,
      })
      setName('')
      refresh()
    } catch (e) {
      setError(String(e))
    }
  }

  return (
    <div className="grid gap-3">
      <h1 className="text-2xl font-semibold">Alerts</h1>

      <Panel title="New Rule" testId="alert-form">
        <div className="flex flex-wrap items-end gap-3 p-3">
          <label className="text-sm">
            <div className="text-xs text-zinc-500">Name (optional)</div>
            <input
              aria-label="Rule name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-44 rounded-sm border border-zinc-700 bg-zinc-950/60 px-2 py-1 font-mono text-sm"
            />
          </label>
          <label className="text-sm">
            <div className="text-xs text-zinc-500">Kind</div>
            <select
              aria-label="Rule kind"
              value={kind}
              onChange={(e) => {
                setKind(e.target.value)
                setParams({})
              }}
              className="rounded-sm border border-zinc-700 bg-zinc-950/60 px-2 py-1 font-mono text-sm"
            >
              {KINDS.map((k) => (
                <option key={k.key} value={k.key}>
                  {k.label}
                </option>
              ))}
            </select>
          </label>
          {kindSpec.needsSymbol && (
            <label className="text-sm">
              <div className="text-xs text-zinc-500">Symbol</div>
              <select
                aria-label="Symbol"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
                className="rounded-sm border border-zinc-700 bg-zinc-950/60 px-2 py-1 font-mono text-sm"
              >
                {(symbolsQuery.data?.watchlist ?? ['BTCUSDT']).map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </label>
          )}
          {kind === 'price_cross' && (
            <label className="text-sm">
              <div className="text-xs text-zinc-500">Direction</div>
              <select
                aria-label="Direction"
                value={direction}
                onChange={(e) =>
                  setDirection(e.target.value as 'above' | 'below')
                }
                className="rounded-sm border border-zinc-700 bg-zinc-950/60 px-2 py-1 font-mono text-sm"
              >
                <option value="above">crosses above</option>
                <option value="below">crosses below</option>
              </select>
            </label>
          )}
          {paramFields(kind).map((f) => (
            <label key={f.name} className="text-sm">
              <div className="text-xs text-zinc-500">{f.label}</div>
              <input
                type="number"
                aria-label={f.label}
                value={params[f.name] ?? f.def}
                step="any"
                onChange={(e) =>
                  setParams((prev) => ({
                    ...prev,
                    [f.name]: Number(e.target.value),
                  }))
                }
                className="w-36 rounded-sm border border-zinc-700 bg-zinc-950/60 px-2 py-1 font-mono text-sm"
              />
            </label>
          ))}
          <button
            onClick={() => void create()}
            className="cursor-pointer rounded bg-amber-500 px-4 py-1.5 text-sm font-semibold text-zinc-950 hover:bg-amber-400"
          >
            Create alert
          </button>
          {error && (
            <span className="text-xs text-red-400" role="alert">
              {error}
            </span>
          )}
        </div>
      </Panel>

      <div className="grid gap-3 lg:grid-cols-2">
        <Panel title="Rules" testId="alert-rules">
          <table className="w-full text-sm">
            <tbody>
              {(rulesQuery.data?.rules ?? []).length === 0 && (
                <tr>
                  <td className="px-3 py-3 font-mono text-xs text-zinc-600">
                    No rules yet — create one above.
                  </td>
                </tr>
              )}
              {(rulesQuery.data?.rules ?? []).map((r) => (
                <tr key={r.id} className="border-t border-zinc-800/60">
                  <td className="px-3 py-1.5 font-medium text-zinc-100">
                    {r.name}
                  </td>
                  <td className="px-3 py-1.5 font-mono text-xs text-zinc-400">
                    {describe(r)}
                  </td>
                  <td className="px-3 py-1.5">
                    <button
                      onClick={() => {
                        void api.toggleAlertRule(r.id).then(refresh)
                      }}
                      className={`cursor-pointer rounded-sm px-2 py-0.5 font-mono text-[10px] uppercase ${
                        r.enabled
                          ? 'bg-emerald-400/10 text-emerald-400'
                          : 'bg-zinc-800 text-zinc-500'
                      }`}
                    >
                      {r.enabled ? 'Armed' : 'Off'}
                    </button>
                  </td>
                  <td className="px-3 py-1.5 text-right">
                    <button
                      onClick={() => {
                        void api.deleteAlertRule(r.id).then(refresh)
                      }}
                      className="cursor-pointer font-mono text-[10px] uppercase text-zinc-600 hover:text-red-400"
                      aria-label={`delete ${r.name}`}
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>

        <Panel title="Event Log" status="live" testId="alert-events">
          <div className="max-h-96 overflow-y-auto font-mono text-[11px]">
            {(eventsQuery.data?.events ?? []).length === 0 && (
              <p className="px-3 py-3 text-zinc-600">No alerts fired yet.</p>
            )}
            {(eventsQuery.data?.events ?? []).map((e) => (
              <div
                key={e.id}
                className="flex justify-between border-l-2 border-amber-400/60 px-3 py-1"
              >
                <span className="text-zinc-100">{e.message}</span>
                <span className="ml-3 shrink-0 text-zinc-600">
                  {e.ts.slice(5, 16)}
                </span>
              </div>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  )
}
