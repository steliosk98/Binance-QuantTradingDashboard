import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import Sparkline from './Sparkline'

describe('Sparkline', () => {
  it('renders a polyline for enough points', () => {
    const { container } = render(<Sparkline values={[1, 2, 3, 2, 5]} />)
    const polyline = container.querySelector('polyline')
    expect(polyline).not.toBeNull()
    expect(polyline!.getAttribute('points')!.split(' ')).toHaveLength(5)
  })

  it('shows placeholder with too few points', () => {
    const { container } = render(<Sparkline values={[1]} />)
    expect(container.querySelector('polyline')).toBeNull()
    expect(container.textContent).toContain('…')
  })

  it('draws baseline when within range', () => {
    const { container } = render(<Sparkline values={[-1, 1]} baseline={0} />)
    expect(container.querySelector('line')).not.toBeNull()
  })
})
