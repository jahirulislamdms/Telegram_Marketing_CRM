import { useEffect, useRef } from 'react'
import type { InboxEvent } from '../api/client'
import { useAuth } from '../store/auth'

/** Opens a WebSocket to the live inbox and invokes `onEvent` for each message. */
export function useInboxSocket(onEvent: (event: InboxEvent) => void) {
  const token = useAuth((s) => s.accessToken)
  const handlerRef = useRef(onEvent)
  handlerRef.current = onEvent

  useEffect(() => {
    if (!token) return
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${window.location.host}/ws/inbox?token=${token}`)
    ws.onmessage = (e) => {
      try {
        handlerRef.current(JSON.parse(e.data) as InboxEvent)
      } catch {
        /* ignore malformed frames */
      }
    }
    return () => ws.close()
  }, [token])
}
