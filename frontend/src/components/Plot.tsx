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

  useEffect(() => {
    if (!ref.current) return
    const el = ref.current
    void Plotly.react(
      el,
      data,
      { ...DARK_LAYOUT, ...layout },
      { responsive: true, displayModeBar: false },
    )
    return () => {
      Plotly.purge(el)
    }
  }, [data, layout])

  return <div ref={ref} data-testid={testId} className="h-full w-full" />
}
