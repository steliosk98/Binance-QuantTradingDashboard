import { create } from 'zustand'

export const INTERVALS = ['1m', '5m', '15m', '1h', '4h', '1d'] as const
export type Interval = (typeof INTERVALS)[number]

interface MarketState {
  symbol: string
  interval: Interval
  setSymbol: (symbol: string) => void
  setInterval: (interval: Interval) => void
}

export const useMarketStore = create<MarketState>((set) => ({
  symbol: 'BTCUSDT',
  interval: '1h',
  setSymbol: (symbol) => set({ symbol }),
  setInterval: (interval) => set({ interval }),
}))
