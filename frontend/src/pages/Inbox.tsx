import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ApiError,
  CONVERSATION_STATUSES,
  accountsApi,
  inboxApi,
  type Conversation,
  type ConversationStatus,
  type InboxEvent,
  type InboxMessage,
  type Thread,
} from '../api/client'
import { useInboxSocket } from '../lib/useInboxSocket'

function errMsg(e: unknown): string {
  if (e instanceof ApiError) return e.message
  return e instanceof Error ? e.message : 'Something went wrong'
}

function upsert(list: Conversation[], conv: Conversation): Conversation[] {
  const rest = list.filter((c) => c.id !== conv.id)
  return [conv, ...rest]
}

export default function Inbox() {
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [thread, setThread] = useState<Thread | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [unreadOnly, setUnreadOnly] = useState(false)
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)
  const selectedRef = useRef<number | null>(null)
  selectedRef.current = selectedId

  const loadConversations = useCallback(async () => {
    try {
      const params: Record<string, string> = {}
      if (unreadOnly) params.unread = 'true'
      setConversations(await inboxApi.listConversations(params))
    } catch (e) {
      setError(errMsg(e))
    }
  }, [unreadOnly])

  useEffect(() => {
    void loadConversations()
  }, [loadConversations])

  const openConversation = async (id: number) => {
    setSelectedId(id)
    try {
      const t = await inboxApi.getThread(id)
      setThread(t)
      await inboxApi.markRead(id)
      setConversations((prev) =>
        prev.map((c) => (c.id === id ? { ...c, unread_count: 0 } : c)),
      )
    } catch (e) {
      setError(errMsg(e))
    }
  }

  // Live updates.
  useInboxSocket((event: InboxEvent) => {
    if (event.type === 'message' && event.conversation && event.message) {
      const conv = event.conversation as Conversation
      const msg = event.message as InboxMessage
      setConversations((prev) => upsert(prev, conv))
      if (selectedRef.current === conv.id) {
        setThread((prev) => {
          if (!prev) return prev
          if (prev.messages.some((m) => m.id === msg.id)) return prev
          return { ...prev, conversation: conv, messages: [...prev.messages, msg] }
        })
      }
    } else if (event.type === 'conversation' && event.conversation) {
      setConversations((prev) => upsert(prev, event.conversation as Conversation))
    }
  })

  const send = async () => {
    if (!selectedId || !text.trim()) return
    setSending(true)
    setError(null)
    try {
      await inboxApi.sendReply(selectedId, { type: 'text', body: text })
      setText('')
      // The outgoing message arrives via the WebSocket broadcast.
    } catch (e) {
      setError(errMsg(e))
    } finally {
      setSending(false)
    }
  }

  const changeStatus = async (status: ConversationStatus) => {
    if (!selectedId) return
    try {
      const conv = await inboxApi.setStatus(selectedId, status)
      setConversations((prev) => prev.map((c) => (c.id === conv.id ? conv : c)))
      setThread((prev) => (prev ? { ...prev, conversation: conv } : prev))
    } catch (e) {
      setError(errMsg(e))
    }
  }

  const simulateIncoming = async () => {
    setError(null)
    try {
      const accounts = (await accountsApi.list()).filter((a) => a.session_ref)
      if (accounts.length === 0) {
        setError('No logged-in account to receive a message.')
        return
      }
      const current = thread?.conversation
      await inboxApi.simulateIncoming({
        account_id: current?.account_id ?? accounts[0].id,
        peer_id: current?.peer_id ?? Math.floor(Math.random() * 1_000_000) + 100000,
        peer_name: current?.label ?? 'Test Lead',
        text: 'Hi! This is an incoming test message.',
      })
    } catch (e) {
      setError(errMsg(e))
    }
  }

  return (
    <div className="page">
      <div className="inbox-head">
        <div>
          <h1 className="page-title">Inbox</h1>
          <p className="page-subtitle">Unified, multi-account live conversations.</p>
        </div>
        <div className="inbox-head-actions">
          <label className="checkbox">
            <input
              type="checkbox"
              checked={unreadOnly}
              onChange={(e) => setUnreadOnly(e.target.checked)}
            />
            <span>Unread only</span>
          </label>
          <button className="btn btn-ghost btn-sm" onClick={simulateIncoming} title="Testing aid">
            Simulate incoming
          </button>
        </div>
      </div>

      {error && <p className="form-error">{error}</p>}

      <div className="inbox-grid">
        {/* Conversation list */}
        <aside className="inbox-list">
          {conversations.length === 0 ? (
            <p className="hint">No conversations yet.</p>
          ) : (
            conversations.map((c) => (
              <button
                key={c.id}
                className={`conv-item${selectedId === c.id ? ' conv-item--active' : ''}`}
                onClick={() => openConversation(c.id)}
              >
                <div className="conv-top">
                  <span className="conv-name">{c.label}</span>
                  {c.unread_count > 0 && <span className="conv-unread">{c.unread_count}</span>}
                </div>
                <div className="conv-preview">{c.last_message_preview || '—'}</div>
                <span className="badge badge--muted conv-status">{c.status.replace('_', ' ')}</span>
              </button>
            ))
          )}
        </aside>

        {/* Chat thread */}
        <section className="inbox-thread">
          {!thread ? (
            <div className="inbox-empty">Select a conversation.</div>
          ) : (
            <>
              <div className="thread-head">
                <span className="thread-title">{thread.conversation.label}</span>
                <select
                  value={thread.conversation.status}
                  onChange={(e) => changeStatus(e.target.value as ConversationStatus)}
                >
                  {CONVERSATION_STATUSES.map((s) => (
                    <option key={s} value={s}>
                      {s.replace('_', ' ')}
                    </option>
                  ))}
                </select>
              </div>
              <div className="thread-body">
                {thread.messages.map((m) => (
                  <div
                    key={m.id}
                    className={`bubble ${m.direction === 'out' ? 'bubble--out' : 'bubble--in'}`}
                  >
                    <div className="bubble-body">{m.body || `[${m.type}]`}</div>
                    <div className="bubble-time">
                      {m.created_at ? new Date(m.created_at).toLocaleTimeString() : ''}
                    </div>
                  </div>
                ))}
              </div>
              <div className="composer">
                <input
                  placeholder="Type a reply…"
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && send()}
                />
                <button className="btn btn-primary" onClick={send} disabled={sending || !text.trim()}>
                  Send
                </button>
              </div>
            </>
          )}
        </section>

        {/* Contact profile */}
        <aside className="inbox-profile">
          {thread?.contact ? (
            <div className="card">
              <div className="card-head">Contact</div>
              <dl className="meta">
                <div>
                  <dt>Name</dt>
                  <dd>{String(thread.contact.label ?? '')}</dd>
                </div>
                <div>
                  <dt>Stage</dt>
                  <dd>{String(thread.contact.stage ?? '')}</dd>
                </div>
                <div>
                  <dt>Source</dt>
                  <dd>{String(thread.contact.source ?? '—')}</dd>
                </div>
                <div>
                  <dt>Consent</dt>
                  <dd>{thread.contact.consent ? '✓' : '—'}</dd>
                </div>
              </dl>
            </div>
          ) : (
            <div className="card">
              <p className="hint">No linked contact.</p>
            </div>
          )}
        </aside>
      </div>
    </div>
  )
}
