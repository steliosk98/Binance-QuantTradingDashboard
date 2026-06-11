import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import Plot from '../components/Plot'

export default function PortfolioPage() {
  const statusQuery = useQuery({
    queryKey: ['portfolio-status'],
    queryFn: api.portfolioStatus,
  })
  const portfolioQuery = useQuery({
    queryKey: ['portfolio'],
    queryFn: api.portfolio,
    enabled: statusQuery.data?.configured === true,
    refetchInterval: 60_000,
  })

  if (statusQuery.data && !statusQuery.data.configured) {
    return (
      <div>
        <h1 className="mb-2 text-2xl font-semibold">Portfolio</h1>
        <p className="text-zinc-400">
          No read-only API keys configured. Add them on the Settings page to see
          balances.
        </p>
      </div>
    )
  }

  const d = portfolioQuery.data
  return (
    <div className="grid gap-4">
      <h1 className="text-2xl font-semibold">Portfolio</h1>
      {portfolioQuery.isLoading && (
        <p className="text-zinc-400" role="status">
          Loading balances…
        </p>
      )}
      {portfolioQuery.isError && (
        <p className="text-red-400" role="alert">
          {String(portfolioQuery.error)}
        </p>
      )}
      {d && (
        <>
          <div className="flex gap-4">
            <div className="rounded border border-zinc-800 p-3">
              <div className="text-xs text-zinc-500">Total (priced assets)</div>
              <div
                className="text-lg font-semibold tabular-nums"
                data-testid="total-usd"
              >
                $
                {d.total_usd.toLocaleString(undefined, {
                  maximumFractionDigits: 2,
                })}
              </div>
            </div>
            <div className="rounded border border-zinc-800 p-3">
              <div className="text-xs text-zinc-500">Account</div>
              <div className="text-sm">
                {d.account_type ?? '—'}{' '}
                {d.can_trade === false && (
                  <span className="text-emerald-400">(read-only)</span>
                )}
              </div>
            </div>
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="overflow-x-auto rounded border border-zinc-800">
              <table className="w-full text-sm" data-testid="balances-table">
                <thead className="bg-zinc-900 text-left text-xs uppercase text-zinc-500">
                  <tr>
                    <th className="px-3 py-2">Asset</th>
                    <th className="px-3 py-2 text-right">Free</th>
                    <th className="px-3 py-2 text-right">Locked</th>
                    <th className="px-3 py-2 text-right">USD value</th>
                  </tr>
                </thead>
                <tbody>
                  {d.balances.map((b) => (
                    <tr key={b.asset} className="border-t border-zinc-800/60">
                      <td className="px-3 py-1.5 font-medium">{b.asset}</td>
                      <td className="px-3 py-1.5 text-right tabular-nums">
                        {b.free}
                      </td>
                      <td className="px-3 py-1.5 text-right tabular-nums">
                        {b.locked}
                      </td>
                      <td className="px-3 py-1.5 text-right tabular-nums">
                        {b.usd_value != null
                          ? `$${b.usd_value.toFixed(2)}`
                          : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="h-80 rounded border border-zinc-800 p-1">
              <Plot
                testId="allocation-pie"
                data={[
                  {
                    type: 'pie',
                    labels: d.balances
                      .filter((b) => b.usd_value)
                      .map((b) => b.asset),
                    values: d.balances
                      .filter((b) => b.usd_value)
                      .map((b) => b.usd_value!),
                    hole: 0.5,
                  },
                ]}
                layout={{ title: { text: 'Allocation' }, showlegend: true }}
              />
            </div>
          </div>
        </>
      )}
    </div>
  )
}
