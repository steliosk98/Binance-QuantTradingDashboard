import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import Panel from './Panel'

export default function FundingExtremes() {
  const q = useQuery({
    queryKey: ['funding-extremes'],
    queryFn: api.fundingExtremes,
    refetchInterval: 60_000,
  })
  const maxAbs = Math.max(
    ...(q.data?.extremes.map((e) => Math.abs(e.annualized_pct)) ?? [1]),
    1,
  )
  return (
    <Panel title="Funding Extremes · Annualized" testId="funding-extremes">
      <div className="max-h-72 overflow-y-auto py-1 font-mono text-[11px]">
        {q.isLoading && (
          <p className="px-3 py-3 text-zinc-600" role="status">
            Loading…
          </p>
        )}
        {q.isError && (
          <p className="px-3 py-3 text-red-400" role="alert">
            {String(q.error)}
          </p>
        )}
        {q.data?.extremes.length === 0 && (
          <p className="px-3 py-3 text-zinc-600">No funding data.</p>
        )}
        {q.data?.extremes.map((e) => (
          <div
            key={e.symbol}
            className="relative flex justify-between px-3 py-1 tabular-nums"
          >
            <div
              className={`absolute inset-y-0.5 left-0 ${
                e.funding_rate >= 0 ? 'bg-emerald-400/10' : 'bg-red-500/10'
              }`}
              style={{
                width: `${(Math.abs(e.annualized_pct) / maxAbs) * 100}%`,
              }}
            />
            <span className="relative font-medium text-zinc-300">
              {e.symbol.replace('USDT', '')}
            </span>
            <span
              className={`relative ${e.funding_rate >= 0 ? 'text-emerald-400' : 'text-red-400'}`}
            >
              {e.annualized_pct >= 0 ? '+' : ''}
              {e.annualized_pct.toFixed(2)}%
            </span>
          </div>
        ))}
      </div>
    </Panel>
  )
}
