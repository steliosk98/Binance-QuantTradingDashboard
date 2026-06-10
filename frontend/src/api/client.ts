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

export const api = {
  candles: (symbol: string, interval: string, limit = 1000) =>
    getJson<CandlesResponse>('/candles', { symbol, interval, limit }),
  symbols: () => getJson<SymbolsResponse>('/symbols'),
  funding: (symbol: string, limit = 500) =>
    getJson<FundingResponse>('/funding', { symbol, limit }),
  openInterest: (symbol: string, limit = 500) =>
    getJson<OpenInterestResponse>('/open-interest', { symbol, limit }),
  tickerSummary: () => getJson<TickerSummaryResponse>('/ticker-summary'),
}
