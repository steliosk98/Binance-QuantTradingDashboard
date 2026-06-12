import { useState } from 'react'
import { api, type OptimizeResponse, type StrategySpec } from '../api/client'
import Panel from './Panel'
import Plot from './Plot'

function gridValues(spec: StrategySpec, name: string, steps = 8): number[] {
  const p = spec.params.find((x) => x.name === name)!
  const out: number[] = []
  for (let i = 0; i < steps; i++) {
    const v = p.min + ((p.max - p.min) * i) / (steps - 1)
    out.push(p.type === 'int' ? Math.round(v) : Number(v.toFixed(2)))
  }
  return [...new Set(out)]
}

export default function Optimizer({
  spec,
  symbol,
  interval,
  baseParams,
  onPick,
}: {
  spec: StrategySpec
  symbol: string
  interval: string
  baseParams: Record<string, number>
  onPick: (params: Record<string, number>) => void
}) {
  const [paramX, setParamX] = useState(spec.params[0]?.name ?? '')
  const [paramY, setParamY] = useState(spec.params[1]?.name ?? '')
  const [result, setResult] = useState<OptimizeResponse | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const run = async () => {
    setBusy(true)
    setError(null)
    try {
      const r = await api.optimize({
        strategy: spec.key,
        symbol,
        interval,
        param_x: paramX,
        param_y: paramY,
        x_values: gridValues(spec, paramX),
        y_values: gridValues(spec, paramY),
        base_params: baseParams,
      })
      setResult(r)
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  if (spec.needs_pair || spec.params.length < 2) return null

  return (
    <Panel title="Parameter Optimizer · Sharpe Grid" testId="optimizer">
      <div className="flex flex-wrap items-end gap-3 p-3">
        {(
          [
            ['X axis', paramX, setParamX],
            ['Y axis', paramY, setParamY],
          ] as const
        ).map(([label, value, set]) => (
          <label key={label} className="text-sm">
            <div className="text-xs text-zinc-500">{label}</div>
            <select
              aria-label={`Optimizer ${label}`}
              value={value}
              onChange={(e) => set(e.target.value)}
              className="rounded-sm border border-zinc-700 bg-zinc-950/60 px-2 py-1 font-mono text-sm"
            >
              {spec.params.map((p) => (
                <option key={p.name} value={p.name}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>
        ))}
        <button
          onClick={() => void run()}
          disabled={busy || paramX === paramY}
          className="cursor-pointer rounded bg-amber-500 px-4 py-1.5 text-sm font-semibold text-zinc-950 hover:bg-amber-400 disabled:opacity-50"
        >
          {busy ? 'Searching…' : 'Run grid search'}
        </button>
        {paramX === paramY && (
          <span className="text-xs text-amber-400">
            pick two different parameters
          </span>
        )}
        {error && (
          <span className="text-xs text-red-400" role="alert">
            {error}
          </span>
        )}
        {result && (
          <span className="font-mono text-xs text-zinc-400">
            best Sharpe{' '}
            <span className="text-emerald-400">
              {result.best.sharpe.toFixed(2)}
            </span>{' '}
            @{' '}
            {Object.entries(result.best.params)
              .map(([k, v]) => `${k}=${v}`)
              .join(' ')}{' '}
            <button
              onClick={() => onPick(result.best.params)}
              className="cursor-pointer text-amber-400 underline-offset-2 hover:underline"
            >
              apply →
            </button>
          </span>
        )}
      </div>
      {result && (
        <div className="h-96 p-2">
          <Plot
            testId="optimizer-heatmap"
            data={[
              {
                type: 'heatmap',
                x: result.x_values.map(String),
                y: result.y_values.map(String),
                z: result.sharpe,
                colorscale: [
                  [0, '#ef5350'],
                  [0.5, '#0c1017'],
                  [1, '#2dd4bf'],
                ],
                colorbar: { title: { text: 'Sharpe' } },
              },
            ]}
            layout={{
              showlegend: false,
              xaxis: { title: { text: result.param_x } },
              yaxis: { title: { text: result.param_y } },
              margin: { t: 16, r: 16, b: 48, l: 64 },
            }}
          />
        </div>
      )}
    </Panel>
  )
}
