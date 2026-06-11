import { useEffect, useRef } from 'react'
import Plotly from 'plotly.js-dist-min'

const DARK_LAYOUT: Partial<Plotly.Layout> = {
  paper_bgcolor: 'transparent',
  plot_bgcolor: 'transparent',
  font: { color: '#94a3b8', size: 10, family: "'JetBrains Mono', monospace" },
  margin: { t: 36, r: 16, b: 40, l: 48 },
  xaxis: { gridcolor: '#161d29', zerolinecolor: '#243044' },
  yaxis: { gridcolor: '#161d29', zerolinecolor: '#243044' },
  showlegend: true,
  legend: { orientation: 'h', y: 1.12 },
  colorway: ['#2dd4bf', '#38bdf8', '#f59e0b', '#a78bfa', '#ef5350', '#f472b6'],
  hoverlabel: {
    bgcolor: '#161d29',
    bordercolor: '#243044',
    font: { color: '#e8edf4', family: "'JetBrains Mono', monospace", size: 11 },
  },
}

export default function Plot({
  data,
  layout,
  testId,
}: {
  data: Plotly.Data[]
  layout?: Partial<Plotly.Layout>
  testId?: string
}) {
  const ref = useRef<HTMLDivElement>(null)
  const lastSpecRef = useRef<string>('')

  // Redraw only when the chart contents actually change. Live ticks make the
  // parent re-render every second with fresh (but equal) data/layout object
  // identities; an unconditional Plotly.react would wipe the hover tooltip
  // out from under the user on each pass.
  useEffect(() => {
    if (!ref.current) return
    const spec = JSON.stringify({ data, layout })
    if (spec === lastSpecRef.current) return
    lastSpecRef.current = spec
    void Plotly.react(
      ref.current,
      data,
      { ...DARK_LAYOUT, ...layout },
      { responsive: true, displayModeBar: false },
    )
  }, [data, layout])

  // Destroy the chart only on unmount, not on every dependency change. Reset
  // the spec guard so a remount (e.g. React StrictMode's double-mount in dev)
  // redraws instead of skipping.
  useEffect(() => {
    const el = ref.current
    return () => {
      lastSpecRef.current = ''
      if (el) Plotly.purge(el)
    }
  }, [])

  return <div ref={ref} data-testid={testId} className="h-full w-full" />
}
