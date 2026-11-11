import { API_BASE_URL } from './api'
import { getToken } from './session'

// The native EventSource API can't send an Authorization header, and this
// app is bearer-token authenticated (not cookies), so the SSE connection is
// driven by hand over fetch's streaming body instead of EventSource.
const INITIAL_RETRY_DELAY_MS = 1000
const MAX_RETRY_DELAY_MS = 10000

/**
 * Subscribes to the server-sent "new_message" push for the current mailbox.
 * Calls `onNewMessage` each time one arrives, and reconnects (with backoff)
 * if the connection drops. Returns a function that stops the subscription.
 */
export function subscribeToMessageStream(onNewMessage: () => void): () => void {
  let stopped = false
  let controller: AbortController | null = null
  let retryDelay = INITIAL_RETRY_DELAY_MS
  let retryTimer: ReturnType<typeof setTimeout> | null = null

  async function connect() {
    if (stopped) return
    const token = getToken()
    if (!token) return

    controller = new AbortController()
    try {
      const response = await fetch(`${API_BASE_URL}/api/messages/stream`, {
        headers: { Authorization: `Bearer ${token}` },
        signal: controller.signal,
      })
      if (!response.ok || !response.body) {
        throw new Error(`stream failed with status ${response.status}`)
      }
      retryDelay = INITIAL_RETRY_DELAY_MS

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (!stopped) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        // SSE frames are separated by a blank line.
        const frames = buffer.split('\n\n')
        buffer = frames.pop() ?? ''
        for (const frame of frames) {
          if (frame.startsWith('event: new_message')) {
            onNewMessage()
          }
        }
      }
    } catch {
      // Connection failed, was aborted (stop()), or dropped: fall through
      // to the reconnect scheduling below. A stop() in flight also lands
      // here since aborting a fetch rejects its promise.
    }

    if (!stopped) {
      retryTimer = setTimeout(() => void connect(), retryDelay)
      retryDelay = Math.min(retryDelay * 2, MAX_RETRY_DELAY_MS)
    }
  }

  void connect()

  return function stop() {
    stopped = true
    controller?.abort()
    if (retryTimer) clearTimeout(retryTimer)
  }
}
