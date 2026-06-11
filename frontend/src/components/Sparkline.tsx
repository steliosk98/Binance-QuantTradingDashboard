/** Tiny SVG sparkline for live rolling values. */
export default function Sparkline({
  values,
  width = 120,
  height = 28,
  color = '#2dd4bf',
  baseline,
  testId,
}: {
  values: number[]
  width?: number
  height?: number
  color?: string
  baseline?: number
  testId?: string
}) {
  if (values.length < 2) {
    return (
      <svg width={width} height={height} data-testid={testId}>
        <text x={4} y={height / 2 + 4} fill="#52525b" fontSize={10}>
          …
        </text>
      </svg>
    )
  }
  const min = Math.min(...values, baseline ?? Infinity)
  const max = Math.max(...values, baseline ?? -Infinity)
  const span = max - min || 1
  const x = (i: number) => (i / (values.length - 1)) * (width - 4) + 2
  const y = (v: number) => height - 3 - ((v - min) / span) * (height - 6)
  const points = values
    .map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`)
    .join(' ')
  return (
    <svg width={width} height={height} data-testid={testId}>
      {baseline != null && baseline >= min && baseline <= max && (
        <line
          x1={0}
          x2={width}
          y1={y(baseline)}
          y2={y(baseline)}
          stroke="#3f3f46"
          strokeDasharray="2 2"
        />
      )}
      <polyline points={points} fill="none" stroke={color} strokeWidth={1.5} />
    </svg>
  )
}
