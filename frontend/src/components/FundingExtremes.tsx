import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'

export default function FundingExtremes() {
  const q = useQuery({
    queryKey: ['funding-extremes'],
    queryFn: api.fundingExtremes,
    refetchInterval: 60_000,
  })
  return (
    <div
      className="rounded border border-zinc-800"
      data-testid="funding-extremes"
    >
      <div className="border-b border-zinc-800 px-3 py-2 text-sm font-medium">
        Funding Extremes (annualized)
      </div>
      <div className="max-h-64 overflow-y-auto text-xs">
        {q.isLoading && (
          <p className="px-3 py-3 text-zinc-500" role="status">
            Loading…
          </p>
        )}
        {q.isError && (
          <p className="px-3 py-3 text-red-400" role="alert">
            {String(q.error)}
          </p>
        )}
        {q.data?.extremes.length === 0 && (
          <p className="px-3 py-3 text-zinc-500">No funding data.</p>
        )}
        {q.data?.extremes.map((e) => (
          <div key={e.symbol} className="flex justify-between px-3 py-1">
            <span className="font-medium">{e.symbol}</span>
            <span
              className={`tabular-nums ${e.funding_rate >= 0 ? 'text-emerald-400' : 'text-red-400'}`}
            >
              {e.annualized_pct.toFixed(2)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
