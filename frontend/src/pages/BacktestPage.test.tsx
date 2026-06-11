import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import BacktestPage from './BacktestPage'
import { renderWithProviders } from '../test/utils'

vi.mock('plotly.js-dist-min', () => ({
  default: { react: vi.fn(), purge: vi.fn() },
}))

const STRATEGIES = {
  strategies: [
    {
      key: 'sma_crossover',
      name: 'SMA Crossover',
      description: 'Long when fast SMA above slow.',
      needs_funding: false,
      params: [
        {
          name: 'fast',
          label: 'Fast period',
          type: 'int',
          default: 20,
          min: 5,
          max: 100,
          step: 1,
        },
        {
          name: 'slow',
          label: 'Slow period',
          type: 'int',
          default: 50,
          min: 10,
          max: 400,
          step: 1,
        },
      ],
    },
  ],
}

const METRICS = {
  total_return: 0.42,
  annualized_return: 0.2,
  sharpe: 1.5,
  sortino: 2.0,
  calmar: 0.9,
  max_drawdown: -0.22,
  win_rate: 0.55,
  profit_factor: 1.8,
  exposure: 0.9,
  turnover: 24,
  n_trades: 12,
  avg_trade_pnl_pct: 0.01,
  bars: 800,
}

const DONE_RESULT = {
  id: 'abc-123',
  created_at: '2026-06-11T00:00:00Z',
  strategy: 'sma_crossover',
  symbol: 'BTCUSDT',
  interval: '1h',
  status: 'done',
  error: null,
  params: { fast: 20, slow: 50 },
  metrics: METRICS,
  equity: [
    ['2026-01-01T00:00:00Z', 1.0, 0.0],
    ['2026-02-01T00:00:00Z', 1.2, -0.05],
    ['2026-03-01T00:00:00Z', 1.42, 0.0],
  ],
  trades: [
    {
      entry_time: '2026-01-02 00:00',
      exit_time: '2026-01-05 00:00',
      direction: 'long',
      entry_price: 100,
      exit_price: 110,
      pnl_pct: 0.1,
      bars: 72,
    },
  ],
  walk_forward: null,
}

function setupFetch(states: string[]) {
  let polls = 0
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.includes('/strategies'))
      return new Response(JSON.stringify(STRATEGIES))
    if (url.includes('/symbols'))
      return new Response(
        JSON.stringify({ watchlist: ['BTCUSDT'], available: [] }),
      )
    if (url.includes('/backtests/abc-123')) {
      const status = states[Math.min(polls, states.length - 1)]
      polls += 1
      return new Response(
        JSON.stringify(
          status === 'done'
            ? DONE_RESULT
            : { ...DONE_RESULT, status, metrics: null },
        ),
      )
    }
    if (url.includes('/backtests') && init?.method === 'POST') {
      return new Response(JSON.stringify({ id: 'abc-123', status: 'pending' }))
    }
    if (url.includes('/backtests')) {
      return new Response(
        JSON.stringify({
          backtests: [
            {
              id: 'abc-123',
              created_at: '2026-06-11T00:00:00Z',
              strategy: 'sma_crossover',
              symbol: 'BTCUSDT',
              interval: '1h',
              status: 'done',
              params: {},
              metrics: METRICS,
            },
          ],
        }),
      )
    }
    return new Response('not found', { status: 404 })
  })
}

describe('BacktestPage', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('renders the param form from the strategy schema', async () => {
    vi.stubGlobal('fetch', setupFetch(['done']))
    renderWithProviders(<BacktestPage />)
    await waitFor(() =>
      expect(screen.getByLabelText('Fast period')).toBeInTheDocument(),
    )
    expect(screen.getByLabelText('Slow period')).toHaveValue(50)
    expect(screen.getByText(/Long when fast SMA/)).toBeInTheDocument()
  })

  it('runs a backtest, polls, and renders results', async () => {
    vi.stubGlobal('fetch', setupFetch(['running', 'done']))
    renderWithProviders(<BacktestPage />)
    await waitFor(() =>
      expect(screen.getByLabelText('Fast period')).toBeInTheDocument(),
    )

    await userEvent.click(screen.getByRole('button', { name: 'Run backtest' }))
    await waitFor(
      () => expect(screen.getByTestId('metrics-cards')).toBeInTheDocument(),
      {
        timeout: 5000,
      },
    )
    expect(screen.getByText('42.00%')).toBeInTheDocument() // total return
    expect(screen.getByTestId('equity-chart')).toBeInTheDocument()
    expect(screen.getByTestId('monthly-heatmap')).toBeInTheDocument()
    expect(screen.getByTestId('trades-table')).toBeInTheDocument()
  })

  it('lists saved backtests', async () => {
    vi.stubGlobal('fetch', setupFetch(['done']))
    renderWithProviders(<BacktestPage />)
    await waitFor(() =>
      expect(screen.getByTestId('saved-backtests')).toHaveTextContent(
        'sma_crossover',
      ),
    )
    expect(screen.getByTestId('saved-backtests')).toHaveTextContent(
      'Sharpe 1.50',
    )
  })
})
