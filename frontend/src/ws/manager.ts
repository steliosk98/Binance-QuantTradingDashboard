/**
 * WebSocket manager: single connection to the backend /ws hub with
 * auto-reconnect (exponential backoff) and automatic resubscription.
 */

export type WsStatus = 'connecting' | 'open' | 'closed'
export type TopicHandler = (data: unknown) => void
type StatusListener = (status: WsStatus) => void

const MAX_BACKOFF_MS = 15_000

export class WsManager {
  private url: string
  private ws: WebSocket | null = null
  private handlers = new Map<string, Set<TopicHandler>>()
  private statusListeners = new Set<StatusListener>()
  private attempt = 0
  private closedByUser = false
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  status: WsStatus = 'closed'

  constructor(url: string) {
    this.url = url
  }

  connect(): void {
    this.closedByUser = false
    if (this.ws && this.ws.readyState <= WebSocket.OPEN) return
    this.setStatus('connecting')
    this.ws = new WebSocket(this.url)
    this.ws.onopen = () => {
      this.attempt = 0
      this.setStatus('open')
      const topics = [...this.handlers.keys()]
      if (topics.length > 0) {
        this.ws?.send(JSON.stringify({ op: 'subscribe', topics }))
      }
    }
    this.ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data as string) as {
          topic?: string
          data?: unknown
        }
        if (msg.topic) {
          this.handlers.get(msg.topic)?.forEach((h) => h(msg.data))
        }
      } catch {
        // ignore malformed frames
      }
    }
    this.ws.onclose = () => {
      this.setStatus('closed')
      this.ws = null
      if (!this.closedByUser) this.scheduleReconnect()
    }
    this.ws.onerror = () => {
      this.ws?.close()
    }
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer) return
    const delay = Math.min(500 * 2 ** this.attempt, MAX_BACKOFF_MS)
    this.attempt += 1
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null
      this.connect()
    }, delay)
  }

  subscribe(topic: string, handler: TopicHandler): () => void {
    let set = this.handlers.get(topic)
    const isNewTopic = !set
    if (!set) {
      set = new Set()
      this.handlers.set(topic, set)
    }
    set.add(handler)
    if (isNewTopic && this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ op: 'subscribe', topics: [topic] }))
    }
    this.connect()
    return () => {
      const handlers = this.handlers.get(topic)
      handlers?.delete(handler)
      if (handlers && handlers.size === 0) {
        this.handlers.delete(topic)
        if (this.ws?.readyState === WebSocket.OPEN) {
          this.ws.send(JSON.stringify({ op: 'unsubscribe', topics: [topic] }))
        }
      }
    }
  }

  onStatus(listener: StatusListener): () => void {
    this.statusListeners.add(listener)
    listener(this.status)
    return () => this.statusListeners.delete(listener)
  }

  private setStatus(status: WsStatus): void {
    this.status = status
    this.statusListeners.forEach((l) => l(status))
  }

  close(): void {
    this.closedByUser = true
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    this.ws?.close()
  }
}

function defaultWsUrl(): string {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${window.location.host}/ws`
}

let instance: WsManager | null = null

export function getWsManager(): WsManager {
  if (!instance) {
    instance = new WsManager(defaultWsUrl())
  }
  return instance
}
