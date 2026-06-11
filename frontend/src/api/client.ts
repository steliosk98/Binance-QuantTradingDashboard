import type { components } from './schema'

export type CandlesResponse = components['schemas']['CandlesResponse']
export type Candle = components['schemas']['CandleOut']
export type SymbolsResponse = components['schemas']['SymbolsResponse']
export type FundingResponse = components['schemas']['FundingResponse']
export type OpenInterestResponse = components['schemas']['OpenInterestResponse']
export type TickerSummary = components['schemas']['TickerSummary']
export type TickerSummaryResponse =
  components['schemas']['TickerSummaryResponse']

const BASE = '/api/v1'

async function getJson<T>(
  path: string,
  params?: Record<string, string | number>,
): Promise<T> {
  const qs = params
    ? '?' +
      new URLSearchParams(
        Object.fromEntries(
          Object.entries(params).map(([k, v]) => [k, String(v)]),
        ),
      ).toString()
    : ''
  const resp = await fetch(`${BASE}${path}${qs}`)
  if (!resp.ok) {
    throw new Error(`GET ${path} failed: ${resp.status}`)
  }
  return resp.json() as Promise<T>
}

export type SeriesPoint = [string, number | null]

export interface IndicatorsResponse {
  symbol: string
  interval: string
  sma_20: SeriesPoint[]
  sma_50: SeriesPoint[]
  ema_20: SeriesPoint[]
  rsi_14: SeriesPoint[]
  macd: SeriesPoint[]
  macd_signal: SeriesPoint[]
  macd_histogram: SeriesPoint[]
  bb_upper: SeriesPoint[]
  bb_middle: SeriesPoint[]
  bb_lower: SeriesPoint[]
  atr_14: SeriesPoint[]
  vwap_session: SeriesPoint[]
  obv: SeriesPoint[]
  stoch_k: SeriesPoint[]
  stoch_d: SeriesPoint[]
  volume_profile: { price: number[]; volume: number[] }
}

export interface ReturnsStats {
  symbol: string
  count: number
  mean: number
  std: number
  skew: number
  kurtosis: number
  jarque_bera_p: number
  histogram: { counts: number[]; edges: number[] }
  qq: { theoretical: number[]; sample: number[] }
}

export interface VolatilityResponse {
  symbol: string
  window: number
  close_to_close: SeriesPoint[]
  parkinson: SeriesPoint[]
  garman_klass: SeriesPoint[]
}

export interface HurstResponse {
  symbol: string
  hurst: number | null
  rolling: SeriesPoint[]
  zscore: SeriesPoint[]
}

export interface CorrelationResponse {
  window_days: number
  symbols: string[]
  matrix: (number | null)[][]
  btc_beta: Record<string, number | null>
}

export interface PairsResponse {
  symbol_a: string
  symbol_b: string
  stat: number
  pvalue: number
  hedge_ratio: number
  cointegrated_5pct: boolean
  spread_z: SeriesPoint[]
}

export interface Regime {
  trend: string
  volatility: string
  funding: string
  adx: number | null
  hurst: number | null
  vol_percentile: number | null
  funding_percentile: number | null
}

export interface RegimeResponse {
  interval: string
  regimes: Record<string, Regime | null>
}

export interface FundingExtreme {
  symbol: string
  funding_rate: number
  annualized_pct: number
}

export interface FundingExtremesResponse {
  extremes: FundingExtreme[]
}

export interface LongShortResponse {
  symbol: string
  entries: { ts: string; ratio: number; long_pct: number; short_pct: number }[]
}

export interface StrategyParam {
  name: string
  label: string
  type: 'int' | 'float'
  default: number
  min: number
  max: number
  step: number
}

export interface StrategySpec {
  key: string
  name: string
  description: string
  needs_funding: boolean
  params: StrategyParam[]
}

export interface BacktestMetrics {
  total_return: number
  annualized_return: number | null
  sharpe: number | null
  sortino: number | null
  calmar: number | null
  max_drawdown: number
  win_rate: number | null
  profit_factor: number | null
  exposure: number
  turnover: number
  n_trades: number
  avg_trade_pnl_pct: number | null
  bars: number
}

export interface BacktestTrade {
  entry_time: string
  exit_time: string
  direction: string
  entry_price: number
  exit_price: number
  pnl_pct: number
  bars: number
}

export interface WalkForwardWindow {
  train: [string, string]
  test: [string, string]
  best_params: Record<string, number>
  in_sample: BacktestMetrics
  out_of_sample: BacktestMetrics
}

export interface BacktestDetail {
  id: string
  created_at: string
  strategy: string
  symbol: string
  interval: string
  status: 'pending' | 'running' | 'done' | 'error'
  error: string | null
  params: Record<string, number> | null
  metrics: BacktestMetrics | null
  equity: [string, number, number][] | null
  trades: BacktestTrade[] | null
  walk_forward: {
    windows: WalkForwardWindow[]
    oos_equity: [string, number][]
    oos_metrics: BacktestMetrics
  } | null
}

export interface BacktestListEntry {
  id: string
  created_at: string
  strategy: string
  symbol: string
  interval: string
  status: string
  params: Record<string, number> | null
  metrics: BacktestMetrics | null
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!resp.ok) {
    throw new Error(`POST ${path} failed: ${resp.status}`)
  }
  return resp.json() as Promise<T>
}

export const api = {
  strategies: () => getJson<{ strategies: StrategySpec[] }>('/strategies'),
  createBacktest: (body: {
    strategy: string
    symbol: string
    interval: string
    params: Record<string, number>
    fee_bps?: number
    slippage_bps?: number
    walk_forward?: boolean
    n_windows?: number
  }) => postJson<{ id: string; status: string }>('/backtests', body),
  getBacktest: (id: string) => getJson<BacktestDetail>(`/backtests/${id}`),
  listBacktests: () =>
    getJson<{ backtests: BacktestListEntry[] }>('/backtests'),
  candles: (symbol: string, interval: string, limit = 1000) =>
    getJson<CandlesResponse>('/candles', { symbol, interval, limit }),
  symbols: () => getJson<SymbolsResponse>('/symbols'),
  funding: (symbol: string, limit = 500) =>
    getJson<FundingResponse>('/funding', { symbol, limit }),
  openInterest: (symbol: string, limit = 500) =>
    getJson<OpenInterestResponse>('/open-interest', { symbol, limit }),
  tickerSummary: () => getJson<TickerSummaryResponse>('/ticker-summary'),
  indicators: (symbol: string, interval: string) =>
    getJson<IndicatorsResponse>('/analytics/indicators', { symbol, interval }),
  returnsStats: (symbol: string, interval: string) =>
    getJson<ReturnsStats>('/analytics/stats/returns', { symbol, interval }),
  volatility: (symbol: string, interval: string, window = 30) =>
    getJson<VolatilityResponse>('/analytics/stats/volatility', {
      symbol,
      interval,
      window,
    }),
  hurst: (symbol: string, interval: string) =>
    getJson<HurstResponse>('/analytics/stats/hurst', { symbol, interval }),
  correlation: (window = 90) =>
    getJson<CorrelationResponse>('/analytics/stats/correlation', { window }),
  regime: () => getJson<RegimeResponse>('/analytics/regime'),
  fundingExtremes: () =>
    getJson<FundingExtremesResponse>('/analytics/funding-extremes'),
  longShort: (symbol: string, limit = 500) =>
    getJson<LongShortResponse>('/long-short', { symbol, limit }),
  pairs: (a: string, b: string, interval: string) =>
    getJson<PairsResponse>('/analytics/stats/pairs', {
      symbol_a: a,
      symbol_b: b,
      interval,
    }),
}
