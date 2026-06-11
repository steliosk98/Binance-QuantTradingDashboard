import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import Panel from './Panel'
import Plot from './Plot'

export default function CorrHeatmap() {
  const q = useQuery({
    queryKey: ['correlation'],
    queryFn: () => api.correlation(90),
  })
  return (
    <Panel title="90-Day Correlation · Daily Log Returns" testId="corr-heatmap">
      <div className="h-80 min-w-0 overflow-hidden p-2">
        {q.isLoading && (
          <p className="p-3 font-mono text-xs text-zinc-600" role="status">
            Computing…
          </p>
        )}
        {q.isError && (
          <p className="p-3 font-mono text-xs text-red-400" role="alert">
            {String(q.error)}
          </p>
        )}
        {q.data && (
          <Plot
            testId="corr-heatmap-plot"
            data={[
              {
                type: 'heatmap',
                x: q.data.symbols.map((s) => s.replace('USDT', '')),
                y: q.data.symbols.map((s) => s.replace('USDT', '')),
                z: q.data.matrix,
                zmin: -1,
                zmax: 1,
                colorscale: [
                  [0, '#ef5350'],
                  [0.5, '#0c1017'],
                  [1, '#2dd4bf'],
                ],
              },
            ]}
            layout={{
              showlegend: false,
              margin: { t: 10, r: 10, b: 40, l: 60 },
            }}
          />
        )}
      </div>
    </Panel>
  )
}
