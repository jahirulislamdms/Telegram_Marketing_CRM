import {
  type ChangeEvent,
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from 'react'
import {
  ApiError,
  CONTACT_STAGES,
  CONVERSATION_STATUSES,
  accountsApi,
  contactsApi,
  inboxApi,
  type Account,
  type Contact,
  type Conversation,
  type ConversationStatus,
  type InboxEvent,
  type InboxMessage,
  type SaveContactInput,
  type Thread,
} from '../api/client'
import { useInboxSocket } from '../lib/useInboxSocket'
import ContactEditModal from '../components/ContactEditModal'

const CONV_PAGE = 20 // conversations per batch — 15.5 §4
const MSG_PAGE = 12 // messages per batch — 15.5 §3

function errMsg(e: unknown): string {
  if (e instanceof ApiError) return e.message
  return e instanceof Error ? e.message : 'Something went wrong'
}

function upsert(list: Conversation[], conv: Conversation): Conversation[] {
  const rest = list.filter((c) => c.id !== conv.id)
  return [conv, ...rest]
}

const MEDIA_TYPES = ['image', 'video', 'gif', 'sticker', 'voice', 'audio', 'file']

const STAGE_BADGE: Record<string, string> = {
  new: 'badge--muted',
  contacted: 'badge--wait',
  replied: 'badge--ok',
  joined: 'badge--ok',
  customer: 'badge--ok',
  opted_out: 'badge--err',
  blocked: 'badge--err',
}

const AVATAR_HUES = [210, 160, 280, 20, 340, 130, 45, 190]

function initialsOf(label: string): string {
  const base = (label || '?').replace(/^[@+]/, '').trim()
  const parts = base.split(/\s+/)
  if (parts.length >= 2 && parts[0] && parts[1]) return (parts[0][0] + parts[1][0]).toUpperCase()
  return base.slice(0, 2).toUpperCase() || '?'
}

function Avatar({ label, id, size }: { label: string; id: number; size?: 'lg' }) {
  const hue = AVATAR_HUES[Math.abs(id) % AVATAR_HUES.length]
  return (
    <span
      className={`c-avatar${size === 'lg' ? ' c-avatar--lg' : ''}`}
      style={{ background: `hsl(${hue} 60% 45%)` }}
      aria-hidden
    >
      {initialsOf(label)}
    </span>
  )
}

function shortTime(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const sameDay = d.toDateString() === now.toDateString()
  if (sameDay) return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  const days = (now.getTime() - d.getTime()) / 86400000
  if (days < 7) return d.toLocaleDateString([], { weekday: 'short' })
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' })
}

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

/** Highlight the in-conversation search term inside a message body (15.5 §7). */
function HighlightedBody({ body, term }: { body: string; term: string }) {
  if (!term.trim()) return <>{body}</>
  const idx = body.toLowerCase().indexOf(term.trim().toLowerCase())
  if (idx < 0) return <>{body}</>
  const end = idx + term.trim().length
  return (
    <>
      {body.slice(0, idx)}
      <mark className="msg-hit">{body.slice(idx, end)}</mark>
      {body.slice(end)}
    </>
  )
}

export default function Inbox() {
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [convTotal, setConvTotal] = useState(0)
  const [loadingConvs, setLoadingConvs] = useState(true)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [thread, setThread] = useState<Thread | null>(null)
  const [messages, setMessages] = useState<InboxMessage[]>([])
  const [hasOlder, setHasOlder] = useState(false)
  const [loadingOlder, setLoadingOlder] = useState(false)
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
  // Inbox vs Archive folder — 15.1.j.
  const [showArchived, setShowArchived] = useState(false)
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)
  const [recording, setRecording] = useState(false)
  // In-conversation search — 15.5 §7.
  const [msgQuery, setMsgQuery] = useState('')
  const [msgHits, setMsgHits] = useState<InboxMessage[] | null>(null)
  const [highlightId, setHighlightId] = useState<number | null>(null)
  const [jumpedBack, setJumpedBack] = useState(false)
  // Contact editing / saving from the panel — 15.5 §5 / §6.
  const [editContact, setEditContact] = useState<Contact | null>(null)
  const [saveOpen, setSaveOpen] = useState(false)
  // Responsive panes — 15.5 §10.
  const [mobileChat, setMobileChat] = useState(false)
  const [panelOpen, setPanelOpen] = useState(false)

  const selectedRef = useRef<number | null>(null)
  selectedRef.current = selectedId
  const fileRef = useRef<HTMLInputElement>(null)
  const recRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const bodyRef = useRef<HTMLDivElement>(null)
  const keepScrollRef = useRef<{ height: number; top: number } | null>(null)
  const toBottomRef = useRef(false)

  // ------------------------------------------------------------ conversations
  const loadConversations = useCallback(
    async (append = false) => {
      if (!append) setLoadingConvs(true)
      try {
        const params: Record<string, string> = {
          limit: String(CONV_PAGE),
          offset: String(append ? conversations.length : 0),
        }
        if (unreadOnly) params.unread = 'true'
        if (showArchived) params.archived = 'true'
        if (selectedAccounts.size > 0) params.account_ids = [...selectedAccounts].join(',')
        if (debouncedSearch.trim()) params.q = debouncedSearch.trim()
        const { items, total } = await inboxApi.listConversationsPage(params)
        setConvTotal(total)
        setConversations((prev) => {
          if (!append) return items
          const seen = new Set(prev.map((c) => c.id))
          return [...prev, ...items.filter((c) => !seen.has(c.id))]
        })
      } catch (e) {
        setError(errMsg(e))
      } finally {
        setLoadingConvs(false)
      }
    },
    // conversations.length is read via the closure only when appending
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [unreadOnly, selectedAccounts, debouncedSearch, showArchived, conversations.length],
  )

  // Reload from the first batch whenever the filters change.
  useEffect(() => {
    void loadConversations(false)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [unreadOnly, selectedAccounts, debouncedSearch, showArchived])

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

  // Keep the composer above the mobile keyboard — 15.5 §11.
  useEffect(() => {
    const vv = window.visualViewport
    if (!vv) return
    const onResize = () => {
      const offset = Math.max(0, window.innerHeight - vv.height - vv.offsetTop)
      document.documentElement.style.setProperty('--kb-offset', `${offset}px`)
      if (offset > 0 && bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight
    }
    vv.addEventListener('resize', onResize)
    vv.addEventListener('scroll', onResize)
    onResize()
    return () => {
      vv.removeEventListener('resize', onResize)
      vv.removeEventListener('scroll', onResize)
    }
  }, [])

  // Restore scroll after prepending older messages / stick to the bottom.
  useLayoutEffect(() => {
    const body = bodyRef.current
    if (!body) return
    if (keepScrollRef.current) {
      const { height, top } = keepScrollRef.current
      body.scrollTop = body.scrollHeight - height + top
      keepScrollRef.current = null
    } else if (toBottomRef.current) {
      body.scrollTop = body.scrollHeight
      toBottomRef.current = false
    }
  }, [messages])

  const resetSearchState = () => {
    setMsgQuery('')
    setMsgHits(null)
    setHighlightId(null)
    setJumpedBack(false)
  }

  const openConversation = async (id: number) => {
    setSelectedId(id)
    setMobileChat(true)
    resetSearchState()
    try {
      const t = await inboxApi.getThread(id) // newest 12 — 15.5 §3
      setThread(t)
      setMessages(t.messages)
      setHasOlder(t.has_more)
      toBottomRef.current = true // open at the newest message
      await inboxApi.markRead(id)
      setConversations((prev) => prev.map((c) => (c.id === id ? { ...c, unread_count: 0 } : c)))
    } catch (e) {
      setError(errMsg(e))
    }
  }

  const loadOlder = async () => {
    if (!selectedId || messages.length === 0 || loadingOlder) return
    setLoadingOlder(true)
    const body = bodyRef.current
    if (body) keepScrollRef.current = { height: body.scrollHeight, top: body.scrollTop }
    try {
      const page = await inboxApi.messages(selectedId, {
        limit: MSG_PAGE,
        before_id: messages[0].id,
      })
      setMessages((prev) => [...page.messages, ...prev])
      setHasOlder(page.has_more)
    } catch (e) {
      setError(errMsg(e))
    } finally {
      setLoadingOlder(false)
    }
  }

  const jumpToLatest = async () => {
    if (!selectedId) return
    try {
      const page = await inboxApi.messages(selectedId, { limit: MSG_PAGE })
      setMessages(page.messages)
      setHasOlder(page.has_more)
      setHighlightId(null)
      setJumpedBack(false)
      toBottomRef.current = true
    } catch (e) {
      setError(errMsg(e))
    }
  }

  // ----------------------------------------------- in-conversation search ---
  const runMessageSearch = async (q: string) => {
    if (!selectedId) return
    if (!q.trim()) {
      setMsgHits(null)
      setHighlightId(null)
      return
    }
    try {
      const page = await inboxApi.messages(selectedId, { q, limit: 50 })
      setMsgHits(page.messages)
    } catch (e) {
      setError(errMsg(e))
    }
  }

  useEffect(() => {
    const t = setTimeout(() => void runMessageSearch(msgQuery), 300)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [msgQuery, selectedId])

  /** Load a window of messages ending at the hit, then scroll to & highlight it. */
  const goToMessage = async (m: InboxMessage) => {
    if (!selectedId) return
    const already = messages.some((x) => x.id === m.id)
    if (!already) {
      try {
        const page = await inboxApi.messages(selectedId, {
          limit: MSG_PAGE,
          before_id: m.id + 1,
        })
        setMessages(page.messages)
        setHasOlder(page.has_more)
        setJumpedBack(true)
      } catch (e) {
        setError(errMsg(e))
        return
      }
    }
    setHighlightId(m.id)
    setPanelOpen(false)
    requestAnimationFrame(() => {
      const el = document.getElementById(`msg-${m.id}`)
      el?.scrollIntoView({ block: 'center', behavior: 'smooth' })
    })
  }

  // ------------------------------------------------------------- actions ----
  const toggleAccount = (id: number) => {
    setSelectedAccounts((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleArchive = async () => {
    if (!thread) return
    setError(null)
    try {
      await inboxApi.archive(thread.conversation.id, !thread.conversation.archived)
      setThread(null)
      setSelectedId(null)
      setMessages([])
      setMobileChat(false)
      await loadConversations(false)
    } catch (e) {
      setError(errMsg(e))
    }
  }

  const deleteConversation = async () => {
    if (!thread) return
    const label = thread.conversation.label
    if (
      !window.confirm(
        `Delete the conversation with ${label} from the CRM?\n\n` +
          'This removes your copy and its message history permanently. ' +
          "It does NOT delete anything from the other person's Telegram.",
      )
    )
      return
    setError(null)
    try {
      await inboxApi.remove(thread.conversation.id)
      setThread(null)
      setSelectedId(null)
      setMessages([])
      setMobileChat(false)
      await loadConversations(false)
    } catch (e) {
      setError(errMsg(e))
    }
  }

  const doSaveContact = async (details: SaveContactInput) => {
    if (!selectedId) return
    setError(null)
    try {
      await inboxApi.saveContact(selectedId, details)
      const t = await inboxApi.getThread(selectedId)
      setThread(t)
      setMessages(t.messages)
      setHasOlder(t.has_more)
      setSaveOpen(false)
      await loadConversations(false)
    } catch (e) {
      setError(errMsg(e))
    }
  }

  const openContactEditor = async () => {
    const cid = thread?.contact?.id
    if (typeof cid !== 'number') return
    try {
      setEditContact(await contactsApi.get(cid))
    } catch (e) {
      setError(errMsg(e))
    }
  }

  const copy = async (value: string | null | undefined) => {
    if (!value) return
    try {
      await navigator.clipboard.writeText(value)
    } catch {
      /* clipboard unavailable */
    }
  }

  // Live updates.
  useInboxSocket((event: InboxEvent) => {
    if (event.type === 'message' && event.conversation && event.message) {
      const conv = event.conversation as Conversation
      const msg = event.message as InboxMessage
      setConversations((prev) => upsert(prev, conv))
      if (selectedRef.current === conv.id) {
        setThread((prev) => (prev ? { ...prev, conversation: conv } : prev))
        setMessages((prev) => {
          if (prev.some((m) => m.id === msg.id)) return prev
          const body = bodyRef.current
          // Only auto-scroll when already near the bottom.
          if (body && body.scrollHeight - body.scrollTop - body.clientHeight < 120)
            toBottomRef.current = true
          return [...prev, msg]
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
      toBottomRef.current = true
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
      toBottomRef.current = true
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
      const list = (await accountsApi.list()).filter((a) => a.session_ref)
      if (list.length === 0) {
        setError('No logged-in account to receive a message.')
        return
      }
      const current = thread?.conversation
      await inboxApi.simulateIncoming({
        account_id: current?.account_id ?? list[0].id,
        peer_id: current?.peer_id ?? Math.floor(Math.random() * 1_000_000) + 100000,
        peer_name: current?.label ?? 'Test Lead',
        text: 'Hi! This is an incoming test message.',
      })
    } catch (e) {
      setError(errMsg(e))
    }
  }

  const contact = thread?.contact as Record<string, unknown> | null | undefined
  const conv = thread?.conversation

  return (
    <div className="page inbox-page">
      <div className="inbox-head">
        <div>
          <h1 className="page-title">Inbox</h1>
          <p className="page-subtitle">Unified, multi-account live conversations.</p>
        </div>
        <div className="inbox-head-actions">
          <div className="folder-tabs">
            <button
              className={`folder-tab${!showArchived ? ' folder-tab--active' : ''}`}
              onClick={() => setShowArchived(false)}
            >
              Inbox
            </button>
            <button
              className={`folder-tab${showArchived ? ' folder-tab--active' : ''}`}
              onClick={() => setShowArchived(true)}
            >
              Archive
            </button>
          </div>
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

      <div className={`inbox-grid${mobileChat ? ' inbox-grid--chat' : ''}`}>
        {/* ------------------------------------------------ conversation list */}
        <aside className="inbox-list">
          {loadingConvs && conversations.length === 0 ? (
            <p className="hint">Loading…</p>
          ) : conversations.length === 0 ? (
            <p className="hint">No conversations yet.</p>
          ) : (
            <>
              {conversations.map((c) => (
                <button
                  key={c.id}
                  className={`conv-item${selectedId === c.id ? ' conv-item--active' : ''}`}
                  onClick={() => openConversation(c.id)}
                >
                  <Avatar label={c.label} id={c.id} />
                  <div className="conv-body">
                    <div className="conv-top">
                      <span className="conv-name">{c.label}</span>
                      <span className="conv-time">{shortTime(c.last_message_at)}</span>
                    </div>
                    {c.peer_username && <div className="conv-user">@{c.peer_username}</div>}
                    <div className="conv-preview">{c.last_message_preview || '—'}</div>
                    <div className="conv-meta-row">
                      <span className={`badge ${STAGE_BADGE[c.status] ?? 'badge--muted'} conv-status`}>
                        {c.status.replace('_', ' ')}
                      </span>
                      <span className="conv-account">via {c.account_label}</span>
                      {c.unread_count > 0 && <span className="conv-unread">{c.unread_count}</span>}
                    </div>
                  </div>
                </button>
              ))}
              {conversations.length < convTotal && (
                <button className="load-more" onClick={() => loadConversations(true)}>
                  Load more conversations ({conversations.length} of {convTotal})
                </button>
              )}
            </>
          )}
        </aside>

        {/* -------------------------------------------------------- chat pane */}
        <section className="inbox-thread">
          {!thread || !conv ? (
            <div className="inbox-empty">Select a conversation.</div>
          ) : (
            <>
              <div className="thread-head">
                <button
                  className="icon-btn thread-back"
                  onClick={() => setMobileChat(false)}
                  title="Back to conversations"
                >
                  ‹
                </button>
                <Avatar label={conv.label} id={conv.id} />
                <div className="thread-head-main">
                  <span className="thread-title">{conv.label}</span>
                  <span className="thread-sub">
                    <span className={`badge ${STAGE_BADGE[conv.status] ?? 'badge--muted'}`}>
                      {conv.status.replace('_', ' ')}
                    </span>
                    <span className="thread-via">via {conv.account_label}</span>
                  </span>
                </div>
                <div className="thread-actions">
                  <select
                    value={conv.status}
                    onChange={(e) => changeStatus(e.target.value as ConversationStatus)}
                  >
                    {CONVERSATION_STATUSES.map((s) => (
                      <option key={s} value={s}>
                        {s.replace('_', ' ')}
                      </option>
                    ))}
                  </select>
                  <button
                    className="btn btn-ghost btn-sm"
                    onClick={toggleArchive}
                    title={
                      conv.archived ? 'Move back to the inbox' : 'Archive this chat (history is kept)'
                    }
                  >
                    {conv.archived ? 'Unarchive' : 'Archive'}
                  </button>
                  <button
                    className="btn btn-ghost btn-sm btn-danger"
                    onClick={deleteConversation}
                    title="Delete our copy of this chat (does not affect their Telegram)"
                  >
                    Delete
                  </button>
                  <button
                    className="icon-btn thread-info"
                    onClick={() => setPanelOpen(true)}
                    title="Contact details"
                  >
                    ⓘ
                  </button>
                </div>
              </div>

              <div className="thread-body" ref={bodyRef}>
                {hasOlder && (
                  <button className="load-older" onClick={loadOlder} disabled={loadingOlder}>
                    {loadingOlder ? 'Loading…' : 'Load older messages'}
                  </button>
                )}
                {messages.map((m) => {
                  const isMedia = MEDIA_TYPES.includes(m.type)
                  return (
                    <div
                      id={`msg-${m.id}`}
                      key={m.id}
                      className={`bubble ${m.direction === 'out' ? 'bubble--out' : 'bubble--in'}${
                        highlightId === m.id ? ' bubble--hit' : ''
                      }`}
                    >
                      {isMedia && <MediaAttachment message={m} />}
                      {m.body ? (
                        <div className="bubble-body">
                          <HighlightedBody body={m.body} term={msgQuery} />
                        </div>
                      ) : (
                        !isMedia && <div className="bubble-body">{`[${m.type}]`}</div>
                      )}
                      <div className="bubble-time">
                        {m.created_at ? new Date(m.created_at).toLocaleTimeString() : ''}
                      </div>
                    </div>
                  )
                })}
                {jumpedBack && (
                  <button className="jump-latest" onClick={jumpToLatest}>
                    Jump to latest ↓
                  </button>
                )}
              </div>

              <div className="composer">
                <input ref={fileRef} type="file" style={{ display: 'none' }} onChange={onAttach} />
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
                <textarea
                  className="composer-input"
                  rows={1}
                  placeholder={recording ? 'Recording… tap ⏹ to send' : 'Type a reply…'}
                  value={text}
                  onChange={(e) => {
                    setText(e.target.value)
                    // Grow with the content, capped by CSS max-height — 15.5 §11.
                    e.target.style.height = 'auto'
                    e.target.style.height = `${Math.min(e.target.scrollHeight, 140)}px`
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault()
                      void send()
                    }
                  }}
                  disabled={recording}
                />
                <button className="btn btn-primary" onClick={send} disabled={sending || !text.trim()}>
                  Send
                </button>
              </div>
            </>
          )}
        </section>

        {/* --------------------------------------------------- contact panel */}
        <aside className={`inbox-profile${panelOpen ? ' inbox-profile--open' : ''}`}>
          <button className="panel-close icon-btn" onClick={() => setPanelOpen(false)} title="Close">
            ✕
          </button>
          {!thread || !conv ? (
            <div className="card">
              <p className="hint">Select a conversation.</p>
            </div>
          ) : (
            <>
              <div className="card">
                <div className="profile-top">
                  <Avatar label={conv.label} id={conv.id} size="lg" />
                  <div>
                    <div className="profile-name">{conv.label}</div>
                    {conv.peer_username && (
                      <div className="profile-user">@{conv.peer_username}</div>
                    )}
                  </div>
                </div>

                <dl className="meta">
                  {conv.peer_id !== null && (
                    <div>
                      <dt>Telegram ID</dt>
                      <dd>{conv.peer_id}</dd>
                    </div>
                  )}
                  <div>
                    <dt>Via account</dt>
                    <dd>{conv.account_label}</dd>
                  </div>
                  {contact && (
                    <>
                      <div>
                        <dt>Phone</dt>
                        <dd>{String(contact.phone ?? '—')}</dd>
                      </div>
                      <div>
                        <dt>Stage</dt>
                        <dd>
                          <span
                            className={`badge ${
                              STAGE_BADGE[String(contact.stage)] ?? 'badge--muted'
                            }`}
                          >
                            {String(contact.stage ?? '').replace('_', ' ')}
                          </span>
                        </dd>
                      </div>
                      <div>
                        <dt>Source</dt>
                        <dd>{String(contact.source ?? '—')}</dd>
                      </div>
                      <div>
                        <dt>Consent</dt>
                        <dd>{contact.consent ? '✓' : '—'}</dd>
                      </div>
                    </>
                  )}
                </dl>

                <div className="profile-actions">
                  {contact ? (
                    <button className="btn btn-primary btn-sm" onClick={openContactEditor}>
                      Edit contact
                    </button>
                  ) : (
                    <button className="btn btn-primary btn-sm" onClick={() => setSaveOpen(true)}>
                      Save as contact
                    </button>
                  )}
                  <button
                    className="btn btn-ghost btn-sm"
                    disabled={!conv.peer_username && !contact?.username}
                    onClick={() =>
                      copy(
                        conv.peer_username
                          ? `@${conv.peer_username}`
                          : contact?.username
                            ? `@${String(contact.username)}`
                            : null,
                      )
                    }
                  >
                    Copy username
                  </button>
                  <button
                    className="btn btn-ghost btn-sm"
                    disabled={!contact?.phone}
                    onClick={() => copy(contact?.phone ? String(contact.phone) : null)}
                  >
                    Copy phone
                  </button>
                </div>
                {!contact && <p className="hint">Not saved in your CRM yet.</p>}
              </div>

              {/* ------------------------------- search in this conversation */}
              <div className="card">
                <div className="card-head">Search in conversation</div>
                <input
                  className="conv-search"
                  placeholder="Find a message…"
                  value={msgQuery}
                  onChange={(e) => setMsgQuery(e.target.value)}
                />
                {msgHits !== null && (
                  <div className="msg-hits">
                    {msgHits.length === 0 ? (
                      <p className="hint">No matching messages.</p>
                    ) : (
                      <>
                        <p className="hint">
                          {msgHits.length} match{msgHits.length === 1 ? '' : 'es'}
                        </p>
                        {msgHits.map((m) => (
                          <button key={m.id} className="msg-hit-row" onClick={() => goToMessage(m)}>
                            <span className="msg-hit-text">{m.body}</span>
                            <span className="msg-hit-time">{shortTime(m.created_at)}</span>
                          </button>
                        ))}
                      </>
                    )}
                  </div>
                )}
              </div>
            </>
          )}
        </aside>
        {panelOpen && <div className="panel-scrim" onClick={() => setPanelOpen(false)} />}
      </div>

      {editContact && (
        <ContactEditModal
          contact={editContact}
          onClose={() => setEditContact(null)}
          onSaved={async () => {
            setEditContact(null)
            if (selectedId) {
              const t = await inboxApi.getThread(selectedId)
              setThread(t)
            }
            await loadConversations(false)
          }}
        />
      )}
      {saveOpen && conv && (
        <SaveContactModal
          conversation={conv}
          onClose={() => setSaveOpen(false)}
          onSave={doSaveContact}
        />
      )}
    </div>
  )
}

/** Save an inbox peer as a contact with full details — 15.5 §6. */
function SaveContactModal({
  conversation,
  onClose,
  onSave,
}: {
  conversation: Conversation
  onClose: () => void
  onSave: (d: SaveContactInput) => Promise<void>
}) {
  const [name, setName] = useState(conversation.label ?? '')
  const [phone, setPhone] = useState('')
  const [username, setUsername] = useState(
    conversation.peer_username ? `@${conversation.peer_username}` : '',
  )
  const [source, setSource] = useState('inbox')
  const [stage, setStage] = useState(
    CONTACT_STAGES.includes(conversation.status as never) ? conversation.status : 'replied',
  )
  const [consent, setConsent] = useState(true)
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    setBusy(true)
    try {
      await onSave({
        name: name.trim() || null,
        phone: phone.trim() || null,
        username: username.trim() || null,
        source: source.trim() || null,
        stage,
        consent,
      })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>Save as contact</h2>
          <button className="icon-btn" onClick={onClose}>
            ✕
          </button>
        </div>
        <div className="field-block">
          <span className="label">Name</span>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Full name" />
        </div>
        <div className="edit-grid">
          <div className="field-block">
            <span className="label">Phone</span>
            <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+15550001234" />
          </div>
          <div className="field-block">
            <span className="label">Username</span>
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="@username"
            />
          </div>
        </div>
        <div className="edit-grid">
          <div className="field-block">
            <span className="label">Source</span>
            <input value={source} onChange={(e) => setSource(e.target.value)} />
          </div>
          <div className="field-block">
            <span className="label">Stage</span>
            <select value={stage} onChange={(e) => setStage(e.target.value)}>
              {CONTACT_STAGES.map((s) => (
                <option key={s} value={s}>
                  {s.replace('_', ' ')}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="field-block">
          <label className="checkbox">
            <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
            <span>Consent to be contacted</span>
          </label>
        </div>
        <div className="modal-actions">
          <button className="btn btn-ghost" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button className="btn btn-primary" onClick={submit} disabled={busy}>
            {busy ? 'Saving…' : 'Save contact'}
          </button>
        </div>
      </div>
    </div>
  )
}
