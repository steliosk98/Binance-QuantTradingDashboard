import type { ReactElement } from 'react'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

/** fetch mock that routes by URL substring; falls back to 404. */
export function routedFetch(routes: Record<string, unknown>) {
  return async (input: RequestInfo | URL) => {
    const url = String(input)
    for (const [fragment, body] of Object.entries(routes)) {
      if (url.includes(fragment)) return new Response(JSON.stringify(body))
    }
    return new Response('not found', { status: 404 })
  }
}

export const EMPTY_CORRELATION = {
  window_days: 90,
  symbols: ['BTC', 'ETH'],
  matrix: [
    [1, 0.8],
    [0.8, 1],
  ],
  btc_beta: {},
}

export function renderWithProviders(ui: ReactElement, { route = '/' } = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchInterval: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
}
