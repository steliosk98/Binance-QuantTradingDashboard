import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ResearchPage from './ResearchPage'
import { renderWithProviders, routedFetch } from '../test/utils'
import { useMarketStore } from '../stores/market'

const plotlyReact = vi.fn()
vi.mock('plotly.js-dist-min', () => ({
  default: {
    react: (...args: unknown[]) => plotlyReact(...args),
    purge: vi.fn(),
  },
}))

const RETURNS = {
  symbol: 'BTCUSDT',
  count: 100,
  mean: 0,
  std: 0.01,
  skew: -0.2,
  kurtosis: 2.1,
  jarque_bera_p: 0.001,
  histogram: { counts: [1, 2, 3], edges: [-0.1, 0, 0.1, 0.2] },
  qq: { theoretical: [-1, 0, 1], sample: [-0.9, 0, 1.1] },
}

const PAIRS = {
  symbol_a: 'BTCUSDT',
  symbol_b: 'ETHUSDT',
  stat: -3.2,
  pvalue: 0.01,
  hedge_ratio: 18.4,
  cointegrated_5pct: true,
  spread_z: [['2024-01-01T00:00:00Z', 0.5]],
}

const ROUTES = {
  '/symbols': { watchlist: ['BTCUSDT', 'ETHUSDT'], available: [] },
  '/stats/returns': RETURNS,
  '/stats/pairs': PAIRS,
}

describe('ResearchPage', () => {
  beforeEach(() => {
    plotlyReact.mockClear()
    useMarketStore.setState({ symbol: 'BTCUSDT', interval: '1h' })
    vi.stubGlobal('fetch', vi.fn(routedFetch(ROUTES)))
  })

  it('renders the distribution tab with stats cards and plots', async () => {
    renderWithProviders(<ResearchPage />)
    await waitFor(() =>
      expect(screen.getByTestId('dist-histogram')).toBeInTheDocument(),
    )
    expect(screen.getByTestId('qq-plot')).toBeInTheDocument()
    expect(screen.getByText('Skew')).toBeInTheDocument()
    expect(screen.getByText('-0.200')).toBeInTheDocument()
    expect(plotlyReact).toHaveBeenCalled()
  })

  it('runs a pairs cointegration test', async () => {
    renderWithProviders(<ResearchPage />)
    await userEvent.click(screen.getByRole('button', { name: 'Pairs' }))
    await userEvent.selectOptions(screen.getByLabelText('Symbol B'), 'ETHUSDT')
    await waitFor(() =>
      expect(screen.getByText(/cointegrated @5%/)).toBeInTheDocument(),
    )
    expect(screen.getByText('18.4000')).toBeInTheDocument()
    expect(screen.getByTestId('spread-z-chart')).toBeInTheDocument()
  })

  it('shows error state when the API fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(routedFetch({ '/symbols': { watchlist: [], available: [] } })),
    )
    renderWithProviders(<ResearchPage />)
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
  })
})
