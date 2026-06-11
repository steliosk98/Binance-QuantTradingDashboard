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

export interface LiveCandle {
  open_time: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export default function CandleChart({
  candles,
  liveCandle,
}: {
  candles: Candle[]
  liveCandle?: LiveCandle | null
}) {
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
      color: liveCandle.close >= liveCandle.open ? '#34d39955' : '#f8717155',
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
