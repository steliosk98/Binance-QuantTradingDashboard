import { useEffect, useRef } from 'react'
import {
  CandlestickSeries,
  ColorType,
  createChart,
  HistogramSeries,
  LineSeries,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from 'lightweight-charts'
import type { Candle, SeriesPoint } from '../api/client'

export interface LiveCandle {
  open_time: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface Overlay {
  id: string
  color: string
  data: SeriesPoint[]
}

export interface PaneSeries {
  id: string
  color: string
  data: SeriesPoint[]
  pane: number
}

function toLineData(
  points: SeriesPoint[],
): { time: UTCTimestamp; value: number }[] {
  return points
    .filter((p): p is [string, number] => p[1] != null)
    .map(([t, v]) => ({
      time: (Date.parse(t) / 1000) as UTCTimestamp,
      value: v,
    }))
}

export default function CandleChart({
  candles,
  liveCandle,
  overlays = [],
  paneSeries = [],
}: {
  candles: Candle[]
  liveCandle?: LiveCandle | null
  overlays?: Overlay[]
  paneSeries?: PaneSeries[]
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  const extraSeriesRef = useRef<Map<string, ISeriesApi<'Line'>>>(new Map())

  useEffect(() => {
    if (!containerRef.current) return
    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#64748b',
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 10,
      },
      grid: {
        vertLines: { color: '#161d29' },
        horzLines: { color: '#161d29' },
      },
      timeScale: { timeVisible: true, secondsVisible: false },
      autoSize: true,
    })
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#2dd4bf',
      downColor: '#ef5350',
      borderVisible: false,
      wickUpColor: '#2dd4bf',
      wickDownColor: '#ef5350',
    })
    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
      color: '#3f3f46',
    })
    chart.priceScale('volume').applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    })
    chartRef.current = chart
    candleSeriesRef.current = candleSeries
    volumeSeriesRef.current = volumeSeries
    const extraSeries = extraSeriesRef.current
    return () => {
      chart.remove()
      chartRef.current = null
      extraSeries.clear()
    }
  }, [])

  // Sync overlay + pane line series with props.
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    const wanted = new Map<
      string,
      { color: string; data: SeriesPoint[]; pane: number }
    >()
    for (const o of overlays)
      wanted.set(o.id, { color: o.color, data: o.data, pane: 0 })
    for (const p of paneSeries)
      wanted.set(p.id, { color: p.color, data: p.data, pane: p.pane })

    for (const [id, series] of extraSeriesRef.current) {
      if (!wanted.has(id)) {
        chart.removeSeries(series)
        extraSeriesRef.current.delete(id)
      }
    }
    for (const [id, spec] of wanted) {
      let series = extraSeriesRef.current.get(id)
      if (!series) {
        series = chart.addSeries(
          LineSeries,
          {
            color: spec.color,
            lineWidth: 1,
            priceLineVisible: false,
            lastValueVisible: false,
          },
          spec.pane,
        )
        extraSeriesRef.current.set(id, series)
      }
      series.setData(toLineData(spec.data))
    }
  }, [overlays, paneSeries])

  useEffect(() => {
    if (!candleSeriesRef.current || !volumeSeriesRef.current) return
    const toTs = (iso: string) => (Date.parse(iso) / 1000) as UTCTimestamp
    candleSeriesRef.current.setData(
      candles.map((c) => ({
        time: toTs(c.open_time),
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      })),
    )
    volumeSeriesRef.current.setData(
      candles.map((c) => ({
        time: toTs(c.open_time),
        value: c.volume,
        color: c.close >= c.open ? '#2dd4bf40' : '#ef535040',
      })),
    )
    chartRef.current?.timeScale().fitContent()
  }, [candles])

  useEffect(() => {
    if (!liveCandle || !candleSeriesRef.current || !volumeSeriesRef.current)
      return
    const time = (Date.parse(liveCandle.open_time) / 1000) as UTCTimestamp
    candleSeriesRef.current.update({
      time,
      open: liveCandle.open,
      high: liveCandle.high,
      low: liveCandle.low,
      close: liveCandle.close,
    })
    volumeSeriesRef.current.update({
      time,
      value: liveCandle.volume,
      color: liveCandle.close >= liveCandle.open ? '#2dd4bf40' : '#ef535040',
    })
  }, [liveCandle])

  return (
    <div
      ref={containerRef}
      data-testid="candle-chart"
      className="h-full w-full"
    />
  )
}
