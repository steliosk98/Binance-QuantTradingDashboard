import { screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import App from './App'
import {
  EMPTY_CORRELATION,
  renderWithProviders,
  routedFetch,
} from './test/utils'

vi.mock('plotly.js-dist-min', () => ({
  default: { react: vi.fn(), purge: vi.fn() },
}))

vi.stubGlobal(
  'fetch',
  vi.fn(
    routedFetch({
      '/auth/status': { auth_enabled: false },
      '/portfolio/status': { configured: true },
      '/correlation': EMPTY_CORRELATION,
      '/ticker-summary': { tickers: [] },
      '/regime': { interval: '1h', regimes: {} },
      '/funding-extremes': { extremes: [] },
    }),
  ),
)

describe('App shell', () => {
  it('renders the top navigation', async () => {
    renderWithProviders(<App />)
    await screen.findByRole('link', { name: 'Portfolio' })
    for (const label of [
      'Dashboard',
      'Chart',
      'Research',
      'Backtest',
      'Paper Trading',
      'Portfolio',
      'Settings',
    ]) {
      expect(screen.getByRole('link', { name: label })).toBeInTheDocument()
    }
    expect(screen.getByText(/Not financial advice/)).toBeInTheDocument()
  })
})
