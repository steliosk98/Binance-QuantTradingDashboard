import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import Plot from './Plot'

export default function CorrHeatmap() {
  const q = useQuery({
    queryKey: ['correlation'],
    queryFn: () => api.correlation(90),
  })
  return (
    <div className="rounded border border-zinc-800" data-testid="corr-heatmap">
      <div className="border-b border-zinc-800 px-3 py-2 text-sm font-medium">
        90-day correlation (daily log returns)
      </div>
      <div className="h-96 p-2">
        {q.isLoading && (
          <p className="p-3 text-zinc-400" role="status">
            Computing…
          </p>
        )}
        {q.isError && (
          <p className="p-3 text-red-400" role="alert">
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
                colorscale: 'RdBu',
                reversescale: true,
              },
            ]}
            layout={{
              showlegend: false,
              margin: { t: 10, r: 10, b: 40, l: 60 },
            }}
          />
        )}
      </div>
    </div>
  )
}
