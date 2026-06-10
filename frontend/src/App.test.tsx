import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from './App'

describe('App shell', () => {
  it('renders the top navigation', () => {
    render(
      <MemoryRouter>
        <App />
      </MemoryRouter>,
    )
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
