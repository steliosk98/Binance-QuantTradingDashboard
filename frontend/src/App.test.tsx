import { screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import App from './App'
import { renderWithProviders } from './test/utils'

vi.stubGlobal(
  'fetch',
  vi.fn(async () => new Response(JSON.stringify({ tickers: [] }))),
)

describe('App shell', () => {
  it('renders the top navigation', () => {
    renderWithProviders(<App />)
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
