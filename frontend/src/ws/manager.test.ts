import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { WsManager } from './manager'

class MockWebSocket {
  static instances: MockWebSocket[] = []
  static OPEN = 1
  readyState = 0
  sent: string[] = []
  onopen: (() => void) | null = null
  onmessage: ((e: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null

  url: string

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }

  send(data: string) {
    this.sent.push(data)
  }

  close() {
    this.readyState = 3
    this.onclose?.()
  }

  // test helpers
  open() {
    this.readyState = 1
    this.onopen?.()
  }

  message(obj: unknown) {
    this.onmessage?.({ data: JSON.stringify(obj) })
  }
}

describe('WsManager', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    vi.stubGlobal('WebSocket', MockWebSocket)
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('subscribes on open and dispatches topic messages', () => {
    const mgr = new WsManager('ws://test/ws')
    const received: unknown[] = []
    mgr.subscribe('tickers', (d) => received.push(d))

    const ws = MockWebSocket.instances[0]
    ws.open()
    expect(JSON.parse(ws.sent[0])).toEqual({
      op: 'subscribe',
      topics: ['tickers'],
    })

    ws.message({ topic: 'tickers', data: { v: 42 } })
    expect(received).toEqual([{ v: 42 }])

    ws.message({ topic: 'other', data: { v: 1 } })
    expect(received).toHaveLength(1)
  })

  it('reconnects after close and resubscribes all topics', () => {
    const mgr = new WsManager('ws://test/ws')
    mgr.subscribe('a', () => {})
    mgr.subscribe('b', () => {})

    const first = MockWebSocket.instances[0]
    first.open()
    first.close() // dropped

    expect(MockWebSocket.instances).toHaveLength(1)
    vi.advanceTimersByTime(600) // first backoff is 500ms
    expect(MockWebSocket.instances).toHaveLength(2)

    const second = MockWebSocket.instances[1]
    second.open()
    const resub = JSON.parse(second.sent[0])
    expect(resub.op).toBe('subscribe')
    expect(resub.topics.sort()).toEqual(['a', 'b'])
    expect(mgr.status).toBe('open')
  })

  it('uses exponential backoff between reconnect attempts', () => {
    const mgr = new WsManager('ws://test/ws')
    mgr.subscribe('a', () => {})
    MockWebSocket.instances[0].open()

    MockWebSocket.instances[0].close()
    vi.advanceTimersByTime(500)
    expect(MockWebSocket.instances).toHaveLength(2)

    MockWebSocket.instances[1].close() // never opened → next backoff 1000ms
    vi.advanceTimersByTime(500)
    expect(MockWebSocket.instances).toHaveLength(2)
    vi.advanceTimersByTime(600)
    expect(MockWebSocket.instances).toHaveLength(3)
  })

  it('unsubscribe removes handler and sends unsubscribe for last handler', () => {
    const mgr = new WsManager('ws://test/ws')
    const unsub = mgr.subscribe('a', () => {})
    const ws = MockWebSocket.instances[0]
    ws.open()
    ws.sent = []
    unsub()
    expect(JSON.parse(ws.sent[0])).toEqual({ op: 'unsubscribe', topics: ['a'] })
  })

  it('does not reconnect after explicit close', () => {
    const mgr = new WsManager('ws://test/ws')
    mgr.subscribe('a', () => {})
    MockWebSocket.instances[0].open()
    mgr.close()
    vi.advanceTimersByTime(60_000)
    expect(MockWebSocket.instances).toHaveLength(1)
  })
})
