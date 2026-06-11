import { screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import DashboardPage from './DashboardPage'
import {
  EMPTY_CORRELATION,
  renderWithProviders,
  routedFetch,
} from '../test/utils'

vi.mock('plotly.js-dist-min', () => ({
  default: { react: vi.fn(), purge: vi.fn() },
}))

const TICKERS = {
  tickers: [
    {
      symbol: 'BTCUSDT',
      last_price: 65432.1,
      change_24h_pct: 2.5,
      volume_24h: 1000,
      quote_volume_24h: 1.5e9,
      funding_rate: 0.0001,
      oi_change_24h_pct: -1.2,
    },
    {
      symbol: 'DOGEUSDT',
      last_price: null,
      change_24h_pct: null,
      volume_24h: null,
      quote_volume_24h: null,
      funding_rate: null,
      oi_change_24h_pct: null,
    },
  ],
}

const REGIMES = {
  interval: '1h',
  regimes: {
    BTCUSDT: {
      trend: 'Trending',
      volatility: 'High Vol',
      funding: 'Crowded Longs',
      adx: 31.2,
      hurst: 0.58,
      vol_percentile: 88,
      funding_percentile: 92,
    },
    DOGEUSDT: null,
  },
}

const EXTREMES = {
  extremes: [
    { symbol: 'DOGEUSDT', funding_rate: -0.002, annualized_pct: -219.0 },
    { symbol: 'BTCUSDT', funding_rate: 0.0001, annualized_pct: 10.95 },
  ],
}

const ROUTES = {
  '/correlation': EMPTY_CORRELATION,
  '/ticker-summary': TICKERS,
  '/regime': REGIMES,
  '/funding-extremes': EXTREMES,
}

describe('DashboardPage', () => {
  it('renders the watchlist table from the API', async () => {
    vi.stubGlobal('fetch', vi.fn(routedFetch(ROUTES)))
    renderWithProviders(<DashboardPage />)
    // Symbols render as base asset + /USDT suffix in the terminal layout
    await waitFor(() =>
      expect(screen.getAllByText('BTC').length).toBeGreaterThan(0),
    )
    expect(screen.getAllByText('+2.50%').length).toBeGreaterThan(0)
    // Missing data renders as em-dashes, not a crash
    expect(screen.getAllByText('DOGE').length).toBeGreaterThan(0)
  })

  it('shows regime labels per symbol', async () => {
    vi.stubGlobal('fetch', vi.fn(routedFetch(ROUTES)))
    renderWithProviders(<DashboardPage />)
    await waitFor(() =>
      expect(screen.getAllByText('Trending').length).toBeGreaterThan(0),
    )
    expect(screen.getAllByText(/High Vol/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Crowded Longs/).length).toBeGreaterThan(0)
  })

  it('ranks funding extremes by magnitude', async () => {
    vi.stubGlobal('fetch', vi.fn(routedFetch(ROUTES)))
    renderWithProviders(<DashboardPage />)
    await waitFor(() =>
      expect(screen.getByTestId('funding-extremes')).toHaveTextContent(
        '-219.00%',
      ),
    )
    const widget = screen.getByTestId('funding-extremes')
    const text = widget.textContent ?? ''
    // DOGE (|-0.002|) listed before BTC (0.0001)
    expect(text.indexOf('DOGE')).toBeLessThan(text.indexOf('BTC'))
  })
})
