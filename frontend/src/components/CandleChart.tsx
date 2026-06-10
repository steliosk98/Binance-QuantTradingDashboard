import { useEffect, useRef } from 'react'
import {
  CandlestickSeries,
  ColorType,
  createChart,
  HistogramSeries,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from 'lightweight-charts'
import type { Candle } from '../api/client'

export default function CandleChart({ candles }: { candles: Candle[] }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null)

  useEffect(() => {
    if (!containerRef.current) return
    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#a1a1aa',
      },
      grid: {
        vertLines: { color: '#27272a' },
        horzLines: { color: '#27272a' },
      },
      timeScale: { timeVisible: true, secondsVisible: false },
      autoSize: true,
    })
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#34d399',
      downColor: '#f87171',
      borderVisible: false,
      wickUpColor: '#34d399',
      wickDownColor: '#f87171',
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
    return () => {
      chart.remove()
      chartRef.current = null
    }
  }, [])

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
        color: c.close >= c.open ? '#34d39955' : '#f8717155',
      })),
    )
    chartRef.current?.timeScale().fitContent()
  }, [candles])

  return (
    <div
      ref={containerRef}
      data-testid="candle-chart"
      className="h-full w-full"
    />
  )
}
