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

describe('DashboardPage', () => {
  it('renders the watchlist table from the API', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        routedFetch({
          '/correlation': EMPTY_CORRELATION,
          '/ticker-summary': TICKERS,
        }),
      ),
    )
    renderWithProviders(<DashboardPage />)
    await waitFor(() => expect(screen.getByText('BTCUSDT')).toBeInTheDocument())
    expect(screen.getByText('+2.50%')).toBeInTheDocument()
    // Missing data renders as em-dashes, not a crash
    expect(screen.getByText('DOGEUSDT')).toBeInTheDocument()
  })
})
