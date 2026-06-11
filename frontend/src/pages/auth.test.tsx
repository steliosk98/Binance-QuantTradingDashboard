import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import PortfolioPage from './PortfolioPage'
import { renderWithProviders, routedFetch } from '../test/utils'
import { useAuthStore } from '../stores/auth'

vi.mock('plotly.js-dist-min', () => ({
  default: { react: vi.fn(), purge: vi.fn() },
}))

describe('Auth gate', () => {
  beforeEach(() => {
    localStorage.clear()
    useAuthStore.setState({ token: null })
  })

  it('shows login when auth enabled and no token', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(routedFetch({ '/auth/status': { auth_enabled: true } })),
    )
    renderWithProviders(<App />)
    await waitFor(() =>
      expect(screen.getByLabelText('Password')).toBeInTheDocument(),
    )
  })

  it('logs in and stores the token', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input)
        if (url.includes('/auth/status'))
          return new Response(JSON.stringify({ auth_enabled: true }))
        if (url.includes('/auth/login') && init?.method === 'POST')
          return new Response(
            JSON.stringify({ token: 'jwt-abc', token_type: 'bearer' }),
          )
        return new Response('not found', { status: 404 })
      }),
    )
    renderWithProviders(<App />)
    await waitFor(() =>
      expect(screen.getByLabelText('Password')).toBeInTheDocument(),
    )
    await userEvent.type(screen.getByLabelText('Password'), 'pw')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    await waitFor(() => expect(useAuthStore.getState().token).toBe('jwt-abc'))
    expect(localStorage.getItem('cryptoquant_token')).toBe('jwt-abc')
  })

  it('skips login when auth disabled', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        routedFetch({
          '/auth/status': { auth_enabled: false },
          '/portfolio/status': { configured: false },
          '/ticker-summary': { tickers: [] },
          '/correlation': {
            window_days: 90,
            symbols: [],
            matrix: [],
            btc_beta: {},
          },
          '/regime': { interval: '1h', regimes: {} },
          '/funding-extremes': { extremes: [] },
        }),
      ),
    )
    renderWithProviders(<App />)
    await waitFor(() =>
      expect(
        screen.getByRole('link', { name: 'Dashboard' }),
      ).toBeInTheDocument(),
    )
    // Portfolio tab hidden without keys
    expect(screen.queryByRole('link', { name: 'Portfolio' })).toBeNull()
  })
})

describe('PortfolioPage', () => {
  it('shows hint when keys are not configured', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(routedFetch({ '/portfolio/status': { configured: false } })),
    )
    renderWithProviders(<PortfolioPage />)
    await waitFor(() =>
      expect(
        screen.getByText(/No read-only API keys configured/),
      ).toBeInTheDocument(),
    )
  })

  it('renders balances when configured', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        routedFetch({
          '/portfolio/status': { configured: true },
          '/portfolio': {
            balances: [
              { asset: 'BTC', free: 0.5, locked: 0, usd_value: 31000 },
              { asset: 'USDT', free: 1000, locked: 0, usd_value: 1000 },
            ],
            total_usd: 32000,
            can_trade: false,
            account_type: 'SPOT',
          },
        }),
      ),
    )
    renderWithProviders(<PortfolioPage />)
    await waitFor(() =>
      expect(screen.getByTestId('balances-table')).toBeInTheDocument(),
    )
    expect(screen.getByTestId('total-usd')).toHaveTextContent('$32,000')
    expect(screen.getByText('BTC')).toBeInTheDocument()
    expect(screen.getByTestId('allocation-pie')).toBeInTheDocument()
  })
})
