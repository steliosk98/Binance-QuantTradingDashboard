import { render } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Plot from './Plot'

const plotlyReact = vi.fn()
vi.mock('plotly.js-dist-min', () => ({
  default: {
    react: (...args: unknown[]) => plotlyReact(...args),
    purge: vi.fn(),
  },
}))

describe('Plot', () => {
  beforeEach(() => plotlyReact.mockClear())

  it('does not redraw when re-rendered with equal data (hover survives live ticks)', () => {
    const { rerender } = render(
      <Plot data={[{ type: 'bar', x: [1], y: [2] }]} testId="p" />,
    )
    const initialCalls = plotlyReact.mock.calls.length
    // Parent re-renders pass fresh-but-equal object identities
    rerender(<Plot data={[{ type: 'bar', x: [1], y: [2] }]} testId="p" />)
    rerender(<Plot data={[{ type: 'bar', x: [1], y: [2] }]} testId="p" />)
    expect(plotlyReact.mock.calls.length).toBe(initialCalls)
  })

  it('redraws when the data actually changes', () => {
    const { rerender } = render(
      <Plot data={[{ type: 'bar', x: [1], y: [2] }]} testId="p" />,
    )
    const initialCalls = plotlyReact.mock.calls.length
    rerender(<Plot data={[{ type: 'bar', x: [1], y: [99] }]} testId="p" />)
    expect(plotlyReact.mock.calls.length).toBe(initialCalls + 1)
  })
})
