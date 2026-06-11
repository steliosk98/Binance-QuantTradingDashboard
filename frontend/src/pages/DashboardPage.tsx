import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api, type Regime, type TickerSummary } from '../api/client'
import CorrHeatmap from '../components/CorrHeatmap'
import FundingExtremes from '../components/FundingExtremes'
import { LiquidationFeed, WhaleFeed } from '../components/LiveFeeds'
import Panel from '../components/Panel'
import Sparkline from '../components/Sparkline'
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
  if (v == null) return 'text-zinc-600'
  return v >= 0 ? 'text-emerald-400' : 'text-red-400'
}

function RegimeBadge({ regime }: { regime: Regime | null | undefined }) {
  if (!regime) return <span className="text-zinc-600">—</span>
  const trendColor =
    regime.trend === 'Trending'
      ? 'border-emerald-400/30 bg-emerald-400/10 text-emerald-400'
      : regime.trend === 'Mean-reverting'
        ? 'border-sky-400/30 bg-sky-400/10 text-sky-400'
        : 'border-zinc-700 bg-zinc-800/60 text-zinc-400'
  return (
    <span className="flex flex-wrap gap-1 font-mono text-[10px] tracking-wide">
      <span className={`rounded-sm border px-1 py-px ${trendColor}`}>
        {regime.trend}
      </span>
      <span className="rounded-sm border border-zinc-700 bg-zinc-800/60 px-1 py-px text-zinc-400">
        {regime.volatility}
      </span>
      {regime.funding !== 'Unknown' && regime.funding !== 'Balanced' && (
        <span className="rounded-sm border border-amber-400/30 bg-amber-400/10 px-1 py-px text-amber-400">
          {regime.funding}
        </span>
      )}
    </span>
  )
}

interface LiveTicker {
  symbol: string
  last: number
  change_pct: number
  quote_volume: number
}

function Row({
  t,
  regime,
  history,
  flash,
}: {
  t: TickerSummary
  regime: Regime | null | undefined
  history: number[]
  flash: 'up' | 'down' | null
}) {
  const setSymbol = useMarketStore((s) => s.setSymbol)
  return (
    <tr
      className={`group border-t border-zinc-800/60 transition-colors hover:bg-zinc-800/40 ${
        flash === 'up'
          ? 'animate-flash-up'
          : flash === 'down'
            ? 'animate-flash-down'
            : ''
      }`}
    >
      <td className="px-3 py-1.5">
        <Link
          to="/chart"
          onClick={() => setSymbol(t.symbol)}
          className="cursor-pointer font-display text-sm font-semibold text-zinc-100 group-hover:text-amber-400"
        >
          {t.symbol.replace('USDT', '')}
          <span className="ml-0.5 text-[10px] font-normal text-zinc-600">
            /USDT
          </span>
        </Link>
      </td>
      <td className="px-2 py-1.5">
        <Sparkline
          values={history}
          width={96}
          height={22}
          color={(t.change_24h_pct ?? 0) >= 0 ? '#2dd4bf' : '#ef5350'}
        />
      </td>
      <td className="px-3 py-1.5 text-right font-mono text-sm text-zinc-100 tabular-nums">
        {fmtPrice(t.last_price)}
      </td>
      <td
        className={`px-3 py-1.5 text-right font-mono text-sm tabular-nums ${pctClass(t.change_24h_pct)}`}
      >
        {fmtPct(t.change_24h_pct)}
      </td>
      <td className="hidden px-3 py-1.5 text-right font-mono text-xs text-zinc-500 tabular-nums md:table-cell">
        {fmtCompact(t.quote_volume_24h)}
      </td>
      <td
        className={`hidden px-3 py-1.5 text-right font-mono text-xs tabular-nums lg:table-cell ${pctClass(t.funding_rate)}`}
      >
        {t.funding_rate == null ? '—' : `${(t.funding_rate * 100).toFixed(4)}%`}
      </td>
      <td
        className={`hidden px-3 py-1.5 text-right font-mono text-xs tabular-nums lg:table-cell ${pctClass(t.oi_change_24h_pct)}`}
      >
        {fmtPct(t.oi_change_24h_pct)}
      </td>
      <td className="hidden px-3 py-1.5 xl:table-cell">
        <RegimeBadge regime={regime} />
      </td>
    </tr>
  )
}

function Kpi({
  label,
  value,
  sub,
  tone = 'neutral',
}: {
  label: string
  value: string
  sub?: string
  tone?: 'up' | 'down' | 'amber' | 'neutral'
}) {
  const toneClass =
    tone === 'up'
      ? 'text-emerald-400'
      : tone === 'down'
        ? 'text-red-400'
        : tone === 'amber'
          ? 'text-amber-400'
          : 'text-zinc-100'
  return (
    <div className="panel-rise rounded-sm border border-zinc-800 bg-zinc-900/80 px-3 py-2">
      <div className="font-mono text-[10px] tracking-[0.14em] text-zinc-500 uppercase">
        {label}
      </div>
      <div
        className={`font-display text-xl font-bold tabular-nums ${toneClass}`}
      >
        {value}
      </div>
      {sub && <div className="font-mono text-[10px] text-zinc-500">{sub}</div>}
    </div>
  )
}

const HISTORY_LEN = 60

interface LiveFeedState {
  tickers: Record<string, LiveTicker>
  history: Record<string, number[]>
  flash: Record<string, 'up' | 'down' | null>
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
  const [feed, setFeed] = useState<LiveFeedState>({
    tickers: {},
    history: {},
    flash: {},
  })

  useTopic('tickers', (data) => {
    const msg = data as { tickers: LiveTicker[] }
    setFeed((prev) => {
      const tickers = { ...prev.tickers }
      const history = { ...prev.history }
      const flash = { ...prev.flash }
      for (const t of msg.tickers) {
        const hist = history[t.symbol] ?? []
        const last = hist[hist.length - 1]
        if (last !== t.last) {
          history[t.symbol] = [...hist.slice(-HISTORY_LEN + 1), t.last]
          flash[t.symbol] = last == null ? null : t.last > last ? 'up' : 'down'
        }
        tickers[t.symbol] = t
      }
      return { tickers, history, flash }
    })
  })
  const live = feed.tickers

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

  const btc = rows.find((r) => r.symbol === 'BTCUSDT')
  const totalVol = rows.reduce((acc, r) => acc + (r.quote_volume_24h ?? 0), 0)
  const gainers = rows.filter((r) => (r.change_24h_pct ?? 0) > 0).length
  const regimes = regimeQuery.data?.regimes
  const trending = regimes
    ? Object.values(regimes).filter((r) => r?.trend === 'Trending').length
    : null
  const btcRegime = regimes?.BTCUSDT

  return (
    <div className="grid gap-3">
      {/* ── KPI command strip ── */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-5">
        <Kpi
          label="BTC / USDT"
          value={fmtPrice(btc?.last_price)}
          sub={fmtPct(btc?.change_24h_pct)}
          tone={(btc?.change_24h_pct ?? 0) >= 0 ? 'up' : 'down'}
        />
        <Kpi
          label="Watchlist 24h Vol"
          value={`$${fmtCompact(totalVol)}`}
          tone="amber"
        />
        <Kpi
          label="Breadth"
          value={rows.length ? `${gainers}/${rows.length}` : '—'}
          sub="advancing"
          tone={gainers >= rows.length / 2 ? 'up' : 'down'}
        />
        <Kpi
          label="Trending Markets"
          value={trending == null ? '—' : `${trending}/10`}
          sub="ADX + Hurst"
        />
        <div className="hidden xl:block">
          <Kpi
            label="BTC Regime"
            value={btcRegime?.trend ?? '—'}
            sub={
              btcRegime
                ? `${btcRegime.volatility} · ${btcRegime.funding}`
                : undefined
            }
            tone={btcRegime?.trend === 'Trending' ? 'up' : 'neutral'}
          />
        </div>
      </div>

      {query.isLoading && (
        <p className="font-mono text-xs text-zinc-500" role="status">
          LOADING WATCHLIST…
        </p>
      )}
      {query.isError && (
        <p className="font-mono text-xs text-red-400" role="alert">
          Failed to load watchlist: {String(query.error)}
        </p>
      )}

      {/* ── Main grid: watchlist + side feeds ── */}
      <div className="grid gap-3 xl:grid-cols-[1fr_360px]">
        {query.data && (
          <Panel title="Watchlist · Live" status="live" className="min-w-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="font-mono text-[10px] tracking-[0.12em] text-zinc-600 uppercase">
                    <th className="px-3 py-1.5 text-left font-medium">
                      Market
                    </th>
                    <th className="px-2 py-1.5 text-left font-medium">
                      1h Tape
                    </th>
                    <th className="px-3 py-1.5 text-right font-medium">Last</th>
                    <th className="px-3 py-1.5 text-right font-medium">24h</th>
                    <th className="hidden px-3 py-1.5 text-right font-medium md:table-cell">
                      Vol
                    </th>
                    <th className="hidden px-3 py-1.5 text-right font-medium lg:table-cell">
                      Funding
                    </th>
                    <th className="hidden px-3 py-1.5 text-right font-medium lg:table-cell">
                      OI Δ
                    </th>
                    <th className="hidden px-3 py-1.5 text-left font-medium xl:table-cell">
                      Regime
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((t) => (
                    <Row
                      key={`${t.symbol}-${feed.flash[t.symbol] ?? ''}-${t.last_price}`}
                      t={t}
                      regime={regimes?.[t.symbol]}
                      history={feed.history[t.symbol] ?? []}
                      flash={feed.flash[t.symbol] ?? null}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        )}
        <div className="grid content-start gap-3">
          <LiquidationFeed />
          <WhaleFeed />
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-[360px_1fr]">
        <FundingExtremes />
        <CorrHeatmap />
      </div>
    </div>
  )
}
