import { type ChangeEvent, useCallback, useEffect, useRef, useState } from 'react'
import {
  ApiError,
  CONVERSATION_STATUSES,
  accountsApi,
  inboxApi,
  type Account,
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

const MEDIA_TYPES = ['image', 'video', 'gif', 'sticker', 'voice', 'audio', 'file']

interface MediaMeta {
  kind?: string
  mime?: string
  name?: string
  size?: number
  duration?: number
}

function parseMeta(ref: string | null): MediaMeta {
  if (!ref) return {}
  try {
    return JSON.parse(ref) as MediaMeta
  } catch {
    return {}
  }
}

function humanSize(n?: number): string {
  if (!n) return ''
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

/** Files download on click (not auto-fetched — a thread may have many). */
function FileChip({ message, meta }: { message: InboxMessage; meta: MediaMeta }) {
  const [busy, setBusy] = useState(false)
  const download = async () => {
    setBusy(true)
    try {
      const blob = await inboxApi.media(message.id)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = meta.name || `file-${message.id}`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      /* unavailable */
    } finally {
      setBusy(false)
    }
  }
  return (
    <button className="media-file" onClick={download} disabled={busy}>
      <span className="media-file-icon">⭳</span>
      <span className="media-file-meta">
        <span className="media-file-name">{meta.name || 'Download file'}</span>
        {meta.size ? <span className="media-file-size">{humanSize(meta.size)}</span> : null}
      </span>
    </button>
  )
}

/** Visual/playable media (image/gif/sticker/video/voice/audio) — streamed from
 *  Telegram as an authed blob, rendered from an object URL. */
function VisualMedia({ message, meta }: { message: InboxMessage; meta: MediaMeta }) {
  const [url, setUrl] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let obj: string | null = null
    let cancelled = false
    inboxApi
      .media(message.id)
      .then((blob) => {
        if (cancelled) return
        obj = URL.createObjectURL(blob)
        setUrl(obj)
      })
      .catch(() => !cancelled && setFailed(true))
    return () => {
      cancelled = true
      if (obj) URL.revokeObjectURL(obj)
    }
  }, [message.id])

  if (failed) return <div className="media-missing">media no longer available</div>
  if (!url) return <div className="media-loading">loading media…</div>

  const t = message.type
  if (t === 'image' || t === 'gif' || t === 'sticker')
    return (
      <img
        className={`media-img${t === 'sticker' ? ' media-sticker' : ''}`}
        src={url}
        alt={meta.name || t}
      />
    )
  if (t === 'video') return <video className="media-video" src={url} controls />
  return <audio className="media-audio" src={url} controls />
}

function MediaAttachment({ message }: { message: InboxMessage }) {
  const meta = parseMeta(message.media_ref)
  if (message.type === 'file') return <FileChip message={message} meta={meta} />
  return <VisualMedia message={message} meta={meta} />
}

export default function Inbox() {
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [thread, setThread] = useState<Thread | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [unreadOnly, setUnreadOnly] = useState(false)
  // Multi-account selection (empty = all accounts) + searchable picker — 15.1.e.
  const [accounts, setAccounts] = useState<Account[]>([])
  const [selectedAccounts, setSelectedAccounts] = useState<Set<number>>(new Set())
  const [acctQuery, setAcctQuery] = useState('')
  const [pickerOpen, setPickerOpen] = useState(false)
  // Conversation search within the current selection — 15.1.g.
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)
  const [recording, setRecording] = useState(false)
  const selectedRef = useRef<number | null>(null)
  selectedRef.current = selectedId
  const fileRef = useRef<HTMLInputElement>(null)
  const recRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])

  const loadConversations = useCallback(async () => {
    try {
      const params: Record<string, string> = {}
      if (unreadOnly) params.unread = 'true'
      if (selectedAccounts.size > 0) params.account_ids = [...selectedAccounts].join(',')
      if (debouncedSearch.trim()) params.q = debouncedSearch.trim()
      setConversations(await inboxApi.listConversations(params))
    } catch (e) {
      setError(errMsg(e))
    }
  }, [unreadOnly, selectedAccounts, debouncedSearch])

  useEffect(() => {
    void loadConversations()
  }, [loadConversations])

  useEffect(() => {
    accountsApi
      .list()
      .then(setAccounts)
      .catch(() => {})
  }, [])

  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 300)
    return () => clearTimeout(t)
  }, [search])

  const toggleAccount = (id: number) => {
    setSelectedAccounts((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const saveContact = async () => {
    if (!selectedId) return
    setError(null)
    try {
      await inboxApi.saveContact(selectedId)
      setThread(await inboxApi.getThread(selectedId))
      await loadConversations()
    } catch (e) {
      setError(errMsg(e))
    }
  }

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

  const doSendMedia = async (file: File, kind: string, caption: string) => {
    if (!selectedId) return
    setSending(true)
    setError(null)
    try {
      await inboxApi.sendMedia(selectedId, file, kind, caption)
      setText('')
      // The outgoing media arrives via the WebSocket broadcast.
    } catch (e) {
      setError(errMsg(e))
    } finally {
      setSending(false)
    }
  }

  const onAttach = (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (f) {
      const m = f.type
      const kind = m.startsWith('image/')
        ? 'image'
        : m.startsWith('video/')
          ? 'video'
          : m.startsWith('audio/')
            ? 'audio'
            : 'file'
      void doSendMedia(f, kind, text)
    }
    e.target.value = ''
  }

  const startRecording = async () => {
    setError(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mimeType = MediaRecorder.isTypeSupported('audio/ogg;codecs=opus')
        ? 'audio/ogg;codecs=opus'
        : 'audio/webm;codecs=opus'
      const rec = new MediaRecorder(stream, { mimeType })
      chunksRef.current = []
      rec.ondataavailable = (ev) => ev.data.size > 0 && chunksRef.current.push(ev.data)
      rec.onstop = () => {
        stream.getTracks().forEach((t) => t.stop())
        const blob = new Blob(chunksRef.current, { type: mimeType })
        const file = new File([blob], 'voice.ogg', { type: mimeType })
        setRecording(false)
        void doSendMedia(file, 'voice', '')
      }
      recRef.current = rec
      rec.start()
      setRecording(true)
    } catch {
      setError('Microphone unavailable or permission denied.')
    }
  }

  const stopRecording = () => recRef.current?.stop()

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
          <div className="acct-picker">
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => setPickerOpen((o) => !o)}
              title="Choose which accounts' inbox to show"
            >
              {selectedAccounts.size === 0
                ? 'All accounts'
                : `${selectedAccounts.size} account${selectedAccounts.size > 1 ? 's' : ''}`}{' '}
              ▾
            </button>
            {pickerOpen && (
              <div className="acct-menu">
                <input
                  className="acct-search"
                  placeholder="Search accounts…"
                  value={acctQuery}
                  onChange={(e) => setAcctQuery(e.target.value)}
                />
                <label className="acct-opt">
                  <input
                    type="checkbox"
                    checked={selectedAccounts.size === 0}
                    onChange={() => setSelectedAccounts(new Set())}
                  />
                  <span>All accounts</span>
                </label>
                {accounts
                  .filter((a) => a.label.toLowerCase().includes(acctQuery.toLowerCase()))
                  .map((a) => (
                    <label className="acct-opt" key={a.id}>
                      <input
                        type="checkbox"
                        checked={selectedAccounts.has(a.id)}
                        onChange={() => toggleAccount(a.id)}
                      />
                      <span>{a.label}</span>
                    </label>
                  ))}
                {accounts.length === 0 && <p className="hint">No accounts yet.</p>}
              </div>
            )}
          </div>
          <input
            className="conv-search"
            placeholder="Search conversations…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
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
                <div className="conv-meta-row">
                  <span className="badge badge--muted conv-status">{c.status.replace('_', ' ')}</span>
                  <span className="conv-account">via {c.account_label}</span>
                </div>
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
                <div className="thread-head-main">
                  <span className="thread-title">{thread.conversation.label}</span>
                  <span className="thread-sub">via {thread.conversation.account_label}</span>
                </div>
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
                {thread.messages.map((m) => {
                  const isMedia = MEDIA_TYPES.includes(m.type)
                  return (
                    <div
                      key={m.id}
                      className={`bubble ${m.direction === 'out' ? 'bubble--out' : 'bubble--in'}`}
                    >
                      {isMedia && <MediaAttachment message={m} />}
                      {m.body ? (
                        <div className="bubble-body">{m.body}</div>
                      ) : (
                        !isMedia && <div className="bubble-body">{`[${m.type}]`}</div>
                      )}
                      <div className="bubble-time">
                        {m.created_at ? new Date(m.created_at).toLocaleTimeString() : ''}
                      </div>
                    </div>
                  )
                })}
              </div>
              <div className="composer">
                <input
                  ref={fileRef}
                  type="file"
                  style={{ display: 'none' }}
                  onChange={onAttach}
                />
                <button
                  className="icon-btn"
                  title="Attach image / video / file"
                  onClick={() => fileRef.current?.click()}
                  disabled={sending || recording}
                >
                  📎
                </button>
                <button
                  className={`icon-btn${recording ? ' icon-btn--recording' : ''}`}
                  title={recording ? 'Stop & send voice' : 'Record voice message'}
                  onClick={recording ? stopRecording : startRecording}
                  disabled={sending}
                >
                  {recording ? '⏹' : '🎤'}
                </button>
                <input
                  placeholder={recording ? 'Recording… tap ⏹ to send' : 'Type a reply…'}
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && send()}
                  disabled={recording}
                />
                <button className="btn btn-primary" onClick={send} disabled={sending || !text.trim()}>
                  Send
                </button>
              </div>
            </>
          )}
        </section>

        {/* Contact / peer profile */}
        <aside className="inbox-profile">
          {!thread ? (
            <div className="card">
              <p className="hint">Select a conversation.</p>
            </div>
          ) : (
            <div className="card">
              <div className="card-head">{thread.contact ? 'Contact' : 'Sender'}</div>
              <dl className="meta">
                <div>
                  <dt>Name</dt>
                  <dd>{thread.conversation.label}</dd>
                </div>
                {thread.conversation.peer_username && (
                  <div>
                    <dt>Username</dt>
                    <dd>@{thread.conversation.peer_username}</dd>
                  </div>
                )}
                {thread.conversation.peer_id !== null && (
                  <div>
                    <dt>Telegram ID</dt>
                    <dd>{thread.conversation.peer_id}</dd>
                  </div>
                )}
                <div>
                  <dt>Via account</dt>
                  <dd>{thread.conversation.account_label}</dd>
                </div>
                {thread.contact && (
                  <>
                    <div>
                      <dt>Phone</dt>
                      <dd>{String(thread.contact.phone ?? '—')}</dd>
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
                  </>
                )}
              </dl>
              {!thread.contact && (
                <>
                  <p className="hint">Not saved in your CRM yet.</p>
                  <button className="btn btn-primary btn-block" onClick={saveContact}>
                    Save as contact
                  </button>
                </>
              )}
            </div>
          )}
        </aside>
      </div>
    </div>
  )
}
