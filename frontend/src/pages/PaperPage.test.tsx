import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PaperPage from './PaperPage'
import { renderWithProviders } from '../test/utils'

vi.mock('plotly.js-dist-min', () => ({
  default: { react: vi.fn(), purge: vi.fn() },
}))

const INSTANCE = {
  id: 'inst-1',
  created_at: '2026-06-11T00:00:00Z',
  name: 'zscore-live',
  strategy: 'zscore_mr',
  symbol: 'BTCUSDT',
  interval: '1m',
  qty_usd: 1000,
  status: 'running',
  params: {},
  guards: {},
  position_qty: -0.0123,
  realized_pnl: 12.34,
  halted_today: false,
}

const DETAIL = {
  ...INSTANCE,
  state: {},
  orders: [
    {
      id: 'o1',
      ts: '2026-06-11T01:00:00Z',
      symbol: 'BTCUSDT',
      side: 'SELL',
      qty: 0.0123,
      price: 62000,
      status: 'filled',
      signal: 'target=-1',
      testnet_order_id: null,
    },
  ],
  equity: [
    ['2026-06-11T00:59:00Z', 1000, 0, 62000],
    ['2026-06-11T01:00:00Z', 1002, -0.0123, 61900],
  ],
}

const calls: string[] = []

function mockFetch() {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    calls.push(`${init?.method ?? 'GET'} ${url}`)
    if (url.includes('/strategies'))
      return new Response(
        JSON.stringify({
          strategies: [
            {
              key: 'zscore_mr',
              name: 'Z-Score MR',
              description: 'fade extremes',
              needs_funding: false,
              params: [
                {
                  name: 'lookback',
                  label: 'Lookback',
                  type: 'int',
                  default: 50,
                  min: 10,
                  max: 500,
                  step: 1,
                },
              ],
            },
          ],
        }),
      )
    if (url.includes('/symbols'))
      return new Response(
        JSON.stringify({ watchlist: ['BTCUSDT'], available: [] }),
      )
    if (url.includes('/paper/instances/inst-1/stop'))
      return new Response(JSON.stringify({ ...INSTANCE, status: 'stopped' }))
    if (url.includes('/paper/instances/inst-1'))
      return new Response(JSON.stringify(DETAIL))
    if (url.includes('/paper/instances') && init?.method === 'POST')
      return new Response(JSON.stringify(INSTANCE), { status: 201 })
    if (url.includes('/paper/instances'))
      return new Response(JSON.stringify({ instances: [INSTANCE] }))
    return new Response('not found', { status: 404 })
  })
}

describe('PaperPage', () => {
  beforeEach(() => {
    calls.length = 0
    vi.stubGlobal('fetch', mockFetch())
  })

  it('lists instances with position and PnL', async () => {
    renderWithProviders(<PaperPage />)
    await waitFor(() =>
      expect(screen.getByText('zscore-live')).toBeInTheDocument(),
    )
    expect(screen.getByText('-0.012300')).toBeInTheDocument()
    expect(screen.getByText('$12.34')).toBeInTheDocument()
    expect(screen.getByText('running')).toBeInTheDocument()
  })

  it('kill switch posts stop', async () => {
    renderWithProviders(<PaperPage />)
    await waitFor(() =>
      expect(screen.getByText('Kill switch')).toBeInTheDocument(),
    )
    await userEvent.click(screen.getByText('Kill switch'))
    await waitFor(() =>
      expect(calls.some((c) => c.includes('POST') && c.includes('/stop'))).toBe(
        true,
      ),
    )
  })

  it('selecting an instance shows orders and equity', async () => {
    renderWithProviders(<PaperPage />)
    await waitFor(() =>
      expect(screen.getByText('zscore-live')).toBeInTheDocument(),
    )
    await userEvent.click(screen.getByText('zscore-live'))
    await waitFor(() =>
      expect(screen.getByTestId('paper-orders')).toBeInTheDocument(),
    )
    expect(screen.getByText('SELL')).toBeInTheDocument()
    expect(screen.getByTestId('paper-equity-chart')).toBeInTheDocument()
  })

  it('creates an instance from the form', async () => {
    renderWithProviders(<PaperPage />)
    await waitFor(() =>
      expect(screen.getByLabelText('Lookback')).toBeInTheDocument(),
    )
    await userEvent.click(
      screen.getByRole('button', { name: 'Create instance' }),
    )
    await waitFor(() =>
      expect(
        calls.some(
          (c) => c.startsWith('POST') && c.endsWith('/paper/instances'),
        ),
      ).toBe(true),
    )
  })
})
