/**
 * WebSocket client with automatic reconnect (exponential backoff, max 30s).
 *
 * Usage:
 *   import { wsClient } from '@/lib/websocket'
 *   const unsub = wsClient.subscribe('alerts', handler)
 *   wsClient.connect('/api/ws/alerts')
 *   // later: unsub()
 */

type MessageHandler = (data: Record<string, unknown>) => void

interface Subscription {
  room: string
  handler: MessageHandler
}

const MAX_BACKOFF_MS = 30_000
const BASE_BACKOFF_MS = 1_000

class WebSocketClient {
  private ws: WebSocket | null = null
  private url: string = ''
  private reconnectTimeout: ReturnType<typeof setTimeout> | null = null
  private attempt = 0
  private subscriptions: Subscription[] = []
  private manualClose = false

  connect(path: string): void {
    const token = typeof window !== 'undefined'
      ? localStorage.getItem('access_token') ?? ''
      : ''
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const host = process.env.NEXT_PUBLIC_API_URL?.replace(/^https?:\/\//, '') ?? 'localhost:8000'
    this.url = `${protocol}://${host}${path}?token=${token}`
    this.manualClose = false
    this._open()
  }

  private _open(): void {
    if (this.ws) {
      this.ws.onclose = null
      this.ws.close()
    }
    this.ws = new WebSocket(this.url)

    this.ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data) as Record<string, unknown>
        const room = (msg.room as string) ?? ''
        for (const sub of this.subscriptions) {
          if (!sub.room || room.startsWith(sub.room)) {
            sub.handler(msg)
          }
        }
      } catch { /* ignore non-JSON frames */ }
    }

    this.ws.onopen = () => {
      this.attempt = 0
    }

    this.ws.onclose = () => {
      if (this.manualClose) return
      const delay = Math.min(BASE_BACKOFF_MS * 2 ** this.attempt, MAX_BACKOFF_MS)
      this.attempt++
      this.reconnectTimeout = setTimeout(() => this._open(), delay)
    }

    this.ws.onerror = () => {
      this.ws?.close()
    }
  }

  /** Register a handler. Returns an unsubscribe function. */
  subscribe(room: string, handler: MessageHandler): () => void {
    const sub: Subscription = { room, handler }
    this.subscriptions.push(sub)
    return () => {
      this.subscriptions = this.subscriptions.filter((s) => s !== sub)
    }
  }

  send(data: unknown): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(typeof data === 'string' ? data : JSON.stringify(data))
    }
  }

  disconnect(): void {
    this.manualClose = true
    if (this.reconnectTimeout) clearTimeout(this.reconnectTimeout)
    this.ws?.close()
    this.ws = null
  }
}

// Named export for targeted use-cases
export const wsClient = new WebSocketClient()

/** Convenience factory — creates an isolated client per page/component. */
export function createWsClient(): WebSocketClient {
  return new WebSocketClient()
}
