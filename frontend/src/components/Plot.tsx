import { useEffect, useRef } from 'react'
import Plotly from 'plotly.js-dist-min'

const DARK_LAYOUT: Partial<Plotly.Layout> = {
  paper_bgcolor: 'transparent',
  plot_bgcolor: 'transparent',
  font: { color: '#a1a1aa', size: 11 },
  margin: { t: 36, r: 16, b: 40, l: 48 },
  xaxis: { gridcolor: '#27272a', zerolinecolor: '#3f3f46' },
  yaxis: { gridcolor: '#27272a', zerolinecolor: '#3f3f46' },
  showlegend: true,
  legend: { orientation: 'h', y: 1.12 },
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
