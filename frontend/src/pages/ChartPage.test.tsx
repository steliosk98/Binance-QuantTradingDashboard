import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ChartPage from './ChartPage'
import { renderWithProviders } from '../test/utils'
import { useMarketStore } from '../stores/market'

const setDataSpy = vi.fn()

vi.mock('lightweight-charts', () => ({
  ColorType: { Solid: 'solid' },
  CandlestickSeries: 'Candlestick',
  HistogramSeries: 'Histogram',
  createChart: () => ({
    addSeries: () => ({ setData: setDataSpy }),
    priceScale: () => ({ applyOptions: vi.fn() }),
    timeScale: () => ({ fitContent: vi.fn() }),
    remove: vi.fn(),
  }),
}))

const CANDLE = {
  open_time: '2024-01-01T00:00:00Z',
  open: 100,
  high: 110,
  low: 95,
  close: 105,
  volume: 12,
  quote_volume: 1200,
  trades: 5,
  taker_buy_volume: 6,
}

function mockFetch(candleCount: number) {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url.includes('/symbols')) {
      return new Response(
        JSON.stringify({ watchlist: ['BTCUSDT', 'ETHUSDT'], available: [] }),
      )
    }
    const params = new URL(url, 'http://test').searchParams
    return new Response(
      JSON.stringify({
        symbol: params.get('symbol'),
        interval: params.get('interval'),
        candles: Array(candleCount).fill(CANDLE),
      }),
    )
  })
}

describe('ChartPage', () => {
  beforeEach(() => {
    setDataSpy.mockClear()
    useMarketStore.setState({ symbol: 'BTCUSDT', interval: '1h' })
  })

  it('fetches candles and feeds them to the chart', async () => {
    const fetchSpy = mockFetch(3)
    vi.stubGlobal('fetch', fetchSpy)
    renderWithProviders(<ChartPage />)

    await waitFor(() =>
      expect(screen.getByTestId('candle-chart')).toBeInTheDocument(),
    )
    // Candle + volume series each receive the 3 candles
    expect(setDataSpy).toHaveBeenCalled()
    expect(setDataSpy.mock.calls[0][0]).toHaveLength(3)
    const candleUrl = fetchSpy.mock.calls
      .map((c) => String(c[0]))
      .find((u) => u.includes('/candles'))
    expect(candleUrl).toContain('symbol=BTCUSDT')
    expect(candleUrl).toContain('interval=1h')
  })

  it('refetches when the interval changes', async () => {
    const fetchSpy = mockFetch(2)
    vi.stubGlobal('fetch', fetchSpy)
    renderWithProviders(<ChartPage />)
    await waitFor(() =>
      expect(screen.getByTestId('candle-chart')).toBeInTheDocument(),
    )

    await userEvent.click(screen.getByRole('button', { name: '5m' }))
    await waitFor(() => {
      const urls = fetchSpy.mock.calls.map((c) => String(c[0]))
      expect(urls.some((u) => u.includes('interval=5m'))).toBe(true)
    })
  })

  it('shows empty state when there is no data', async () => {
    vi.stubGlobal('fetch', mockFetch(0))
    renderWithProviders(<ChartPage />)
    await waitFor(() =>
      expect(screen.getByText(/No data for BTCUSDT/)).toBeInTheDocument(),
    )
  })

  it('shows error state on fetch failure', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('boom', { status: 500 })),
    )
    renderWithProviders(<ChartPage />)
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
  })
})
