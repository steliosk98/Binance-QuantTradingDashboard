import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api, type Regime, type TickerSummary } from '../api/client'
import CorrHeatmap from '../components/CorrHeatmap'
import FundingExtremes from '../components/FundingExtremes'
import { LiquidationFeed, WhaleFeed } from '../components/LiveFeeds'
import { useMarketStore } from '../stores/market'
import { useTopic } from '../ws/hooks'

function fmtPrice(v: number | null | undefined): string {
  if (v == null) return '—'
  return v >= 100
    ? v.toLocaleString(undefined, { maximumFractionDigits: 2 })
    : v.toPrecision(5)
}

function fmtPct(v: number | null | undefined): string {
  if (v == null) return '—'
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`
}

function fmtCompact(v: number | null | undefined): string {
  if (v == null) return '—'
  return Intl.NumberFormat(undefined, {
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(v)
}

function pctClass(v: number | null | undefined): string {
  if (v == null) return 'text-zinc-500'
  return v >= 0 ? 'text-emerald-400' : 'text-red-400'
}

function RegimeBadge({ regime }: { regime: Regime | null | undefined }) {
  if (!regime) return <span className="text-zinc-600">—</span>
  const color =
    regime.trend === 'Trending'
      ? 'text-emerald-400'
      : regime.trend === 'Mean-reverting'
        ? 'text-blue-400'
        : 'text-zinc-400'
  return (
    <span className="text-xs">
      <span className={color}>{regime.trend}</span>
      <span className="text-zinc-500"> · {regime.volatility}</span>
      {regime.funding !== 'Unknown' && (
        <span
          className={
            regime.funding === 'Balanced' ? 'text-zinc-500' : 'text-amber-400'
          }
        >
          {' '}
          · {regime.funding}
        </span>
      )}
    </span>
  )
}

function Row({
  t,
  regime,
}: {
  t: TickerSummary
  regime: Regime | null | undefined
}) {
  const setSymbol = useMarketStore((s) => s.setSymbol)
  return (
    <tr className="border-b border-zinc-800/60 hover:bg-zinc-800/40">
      <td className="px-3 py-2 font-medium">
        <Link
          to="/chart"
          onClick={() => setSymbol(t.symbol)}
          className="hover:text-emerald-400"
        >
          {t.symbol}
        </Link>
      </td>
      <td className="px-3 py-2 text-right tabular-nums">
        {fmtPrice(t.last_price)}
      </td>
      <td
        className={`px-3 py-2 text-right tabular-nums ${pctClass(t.change_24h_pct)}`}
      >
        {fmtPct(t.change_24h_pct)}
      </td>
      <td className="px-3 py-2 text-right tabular-nums text-zinc-400">
        {fmtCompact(t.quote_volume_24h)}
      </td>
      <td
        className={`px-3 py-2 text-right tabular-nums ${pctClass(t.funding_rate)}`}
      >
        {t.funding_rate == null ? '—' : `${(t.funding_rate * 100).toFixed(4)}%`}
      </td>
      <td
        className={`px-3 py-2 text-right tabular-nums ${pctClass(t.oi_change_24h_pct)}`}
      >
        {fmtPct(t.oi_change_24h_pct)}
      </td>
      <td className="px-3 py-2">
        <RegimeBadge regime={regime} />
      </td>
    </tr>
  )
}

interface LiveTicker {
  symbol: string
  last: number
  change_pct: number
  quote_volume: number
}

export default function DashboardPage() {
  const query = useQuery({
    queryKey: ['ticker-summary'],
    queryFn: api.tickerSummary,
    refetchInterval: 30000,
  })
  const regimeQuery = useQuery({
    queryKey: ['regime'],
    queryFn: api.regime,
    refetchInterval: 120_000,
  })
  const [live, setLive] = useState<Record<string, LiveTicker>>({})
  useTopic('tickers', (data) => {
    const msg = data as { tickers: LiveTicker[] }
    setLive((prev) => {
      const next = { ...prev }
      for (const t of msg.tickers) next[t.symbol] = t
      return next
    })
  })

  const rows = (query.data?.tickers ?? []).map((t) => {
    const lt = live[t.symbol]
    return lt
      ? {
          ...t,
          last_price: lt.last,
          change_24h_pct: lt.change_pct,
          quote_volume_24h: lt.quote_volume,
        }
      : t
  })

  return (
    <div>
      <h1 className="mb-4 text-2xl font-semibold">Dashboard</h1>
      {query.isLoading && (
        <p className="text-zinc-400" role="status">
          Loading watchlist…
        </p>
      )}
      {query.isError && (
        <p className="text-red-400" role="alert">
          Failed to load watchlist: {String(query.error)}
        </p>
      )}
      {query.data && (
        <div className="overflow-x-auto rounded border border-zinc-800">
          <table className="w-full text-sm">
            <thead className="bg-zinc-900 text-left text-xs uppercase text-zinc-500">
              <tr>
                <th className="px-3 py-2">Symbol</th>
                <th className="px-3 py-2 text-right">Price</th>
                <th className="px-3 py-2 text-right">24h %</th>
                <th className="px-3 py-2 text-right">24h Vol (quote)</th>
                <th className="px-3 py-2 text-right">Funding</th>
                <th className="px-3 py-2 text-right">OI Δ 24h</th>
                <th className="px-3 py-2">Regime</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((t) => (
                <Row
                  key={t.symbol}
                  t={t}
                  regime={regimeQuery.data?.regimes[t.symbol]}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="mt-4 grid gap-4 md:grid-cols-3">
        <LiquidationFeed />
        <WhaleFeed />
        <FundingExtremes />
      </div>
      <div className="mt-4">
        <CorrHeatmap />
      </div>
    </div>
  )
}
