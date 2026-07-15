import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import {
  ApiError,
  botsApi,
  type Bot,
  type BotConversation,
  type BotDetail,
  type BotThread,
  type InboxEvent,
} from '../api/client'
import { useInboxSocket } from '../lib/useInboxSocket'

const BOT_BADGE: Record<string, string> = {
  running: 'badge--ok',
  stopped: 'badge--muted',
  error: 'badge--err',
}

function errMsg(e: unknown): string {
  if (e instanceof ApiError) return e.message
  return e instanceof Error ? e.message : 'Something went wrong'
}

export default function Bots() {
  const [bots, setBots] = useState<Bot[]>([])
  const [detail, setDetail] = useState<BotDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  const loadBots = async () => {
    try {
      setBots(await botsApi.list())
    } catch (e) {
      setError(errMsg(e))
    }
  }

  useEffect(() => {
    void loadBots()
  }, [])

  const open = async (id: number) => {
    try {
      setDetail(await botsApi.get(id))
    } catch (e) {
      setError(errMsg(e))
    }
  }

  const control = async (fn: () => Promise<unknown>) => {
    setError(null)
    try {
      await fn()
      await loadBots()
      if (detail) setDetail(await botsApi.get(detail.id))
    } catch (e) {
      setError(errMsg(e))
    }
  }

  return (
    <div className="page">
      <h1 className="page-title">Bots</h1>
      <p className="page-subtitle">
        Host multiple bots by pasting a BotFather token: two-way bot inbox, channel posts,
        broadcasts, subscribers, and UTM opt-in deep-links.
      </p>
      {error && <p className="form-error">{error}</p>}

      <div className="warmup-grid">
        <div>
          <AddBotCard onAdded={loadBots} onError={setError} />
          <section className="card">
            <div className="card-head">Bots</div>
            {bots.length === 0 ? (
              <p className="hint">No bots yet.</p>
            ) : (
              <ul className="run-list">
                {bots.map((b) => (
                  <li
                    key={b.id}
                    className={`run-item${detail?.id === b.id ? ' run-item--active' : ''}`}
                    onClick={() => open(b.id)}
                  >
                    <span>{b.name || b.username || `Bot #${b.id}`}</span>
                    <span className={`badge ${BOT_BADGE[b.status] ?? 'badge--muted'}`}>{b.status}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
        <div>
          {!detail ? (
            <section className="card">
              <p className="hint">Select a bot to manage it.</p>
            </section>
          ) : (
            <BotDetailView bot={detail} onControl={control} onError={setError} />
          )}
        </div>
      </div>
    </div>
  )
}

function AddBotCard({ onAdded, onError }: { onAdded: () => void; onError: (m: string) => void }) {
  const [token, setToken] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      await botsApi.add(token)
      setToken('')
      onAdded()
    } catch (err) {
      onError(errMsg(err))
    } finally {
      setBusy(false)
    }
  }
  return (
    <section className="card">
      <div className="card-head">Add bot (BotFather token)</div>
      <form className="form-row" onSubmit={submit}>
        <input placeholder="123456:ABC-DEF…" required value={token} onChange={(e) => setToken(e.target.value)} />
        <button className="btn btn-primary" type="submit" disabled={busy || !token}>
          Add
        </button>
      </form>
    </section>
  )
}

function BotDetailView({
  bot,
  onControl,
  onError,
}: {
  bot: BotDetail
  onControl: (fn: () => Promise<unknown>) => void
  onError: (m: string) => void
}) {
  const [convs, setConvs] = useState<BotConversation[]>([])
  const [thread, setThread] = useState<BotThread | null>(null)
  const [text, setText] = useState('')
  const selectedRef = useRef<number | null>(null)

  const loadConvs = useCallback(async () => {
    try {
      setConvs(await botsApi.conversations(bot.id))
    } catch (e) {
      onError(errMsg(e))
    }
  }, [bot.id, onError])

  useEffect(() => {
    void loadConvs()
    setThread(null)
    selectedRef.current = null
  }, [loadConvs])

  useInboxSocket((event: InboxEvent) => {
    if (event.type === 'bot_message') {
      void loadConvs()
      const convId = (event.conversation as { id?: number } | undefined)?.id
      if (convId && convId === selectedRef.current) void openConv(convId)
    }
  })

  const openConv = async (cid: number) => {
    selectedRef.current = cid
    try {
      setThread(await botsApi.thread(bot.id, cid))
      await botsApi.markRead(bot.id, cid)
      void loadConvs()
    } catch (e) {
      onError(errMsg(e))
    }
  }

  const send = async () => {
    if (!thread || !text.trim()) return
    try {
      await botsApi.reply(bot.id, thread.conversation.id, text)
      setText('')
    } catch (e) {
      onError(errMsg(e))
    }
  }

  const simulate = async () => {
    try {
      await botsApi.simulateIncoming(bot.id, {
        telegram_user_id: Math.floor(Math.random() * 900000) + 100000,
        name: 'Test User',
        text: 'Hi! Testing the bot inbox.',
        utm_source: 'instagram',
      })
    } catch (e) {
      onError(errMsg(e))
    }
  }

  return (
    <>
      <section className="card">
        <div className="run-detail-head">
          <div>
            <h2 className="run-title">{bot.name || bot.username || `Bot #${bot.id}`}</h2>
            <span className={`badge ${BOT_BADGE[bot.status] ?? 'badge--muted'}`}>{bot.status}</span>{' '}
            <span className="hint-inline">
              started {bot.counts.started ?? 0} · active {bot.counts.active ?? 0} · subscribed{' '}
              {bot.counts.subscribed ?? 0}
            </span>
          </div>
          <div className="run-controls">
            {bot.status !== 'running' ? (
              <button className="btn btn-primary btn-sm" onClick={() => onControl(() => botsApi.start(bot.id))}>
                Start
              </button>
            ) : (
              <button className="btn btn-ghost btn-sm" onClick={() => onControl(() => botsApi.stop(bot.id))}>
                Stop
              </button>
            )}
            <button className="btn btn-ghost btn-sm" onClick={() => onControl(() => botsApi.remove(bot.id))}>
              Remove
            </button>
          </div>
        </div>
        <p className="hint">Opt-in deep-link: {bot.deep_link}</p>
      </section>

      <PostBroadcastCard bot={bot} onError={onError} />

      <section className="card">
        <div className="card-head">
          Bot inbox
          <button className="btn btn-ghost btn-sm" style={{ float: 'right' }} onClick={simulate}>
            Simulate incoming
          </button>
        </div>
        <div className="inbox-grid" style={{ gridTemplateColumns: '240px 1fr', height: 340 }}>
          <aside className="inbox-list">
            {convs.length === 0 ? (
              <p className="hint">No conversations.</p>
            ) : (
              convs.map((c) => (
                <button
                  key={c.id}
                  className={`conv-item${thread?.conversation.id === c.id ? ' conv-item--active' : ''}`}
                  onClick={() => openConv(c.id)}
                >
                  <div className="conv-top">
                    <span className="conv-name">{c.label}</span>
                    {c.unread_count > 0 && <span className="conv-unread">{c.unread_count}</span>}
                  </div>
                  <div className="conv-preview">{c.last_message_preview || '—'}</div>
                </button>
              ))
            )}
          </aside>
          <section className="inbox-thread">
            {!thread ? (
              <div className="inbox-empty">Select a conversation.</div>
            ) : (
              <>
                <div className="thread-body">
                  {thread.messages.map((m) => (
                    <div key={m.id} className={`bubble ${m.direction === 'out' ? 'bubble--out' : 'bubble--in'}`}>
                      <div className="bubble-body">{m.body}</div>
                    </div>
                  ))}
                </div>
                <div className="composer">
                  <input
                    placeholder="Reply…"
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && send()}
                  />
                  <button className="btn btn-primary" onClick={send} disabled={!text.trim()}>
                    Send
                  </button>
                </div>
              </>
            )}
          </section>
        </div>
      </section>
    </>
  )
}

function PostBroadcastCard({ bot, onError }: { bot: BotDetail; onError: (m: string) => void }) {
  const [chatId, setChatId] = useState('')
  const [postText, setPostText] = useState('')
  const [imageUrl, setImageUrl] = useState('')
  const [broadcastText, setBroadcastText] = useState('')
  const [note, setNote] = useState<string | null>(null)

  const post = async () => {
    setNote(null)
    try {
      await botsApi.post(bot.id, { chat_id: chatId, text: postText, image_url: imageUrl || null })
      setNote('Posted to channel.')
      setPostText('')
      setImageUrl('')
    } catch (e) {
      onError(errMsg(e))
    }
  }
  const broadcast = async () => {
    setNote(null)
    try {
      const r = await botsApi.broadcast(bot.id, broadcastText)
      setNote(`Broadcast sent to ${r.sent}/${r.recipients} subscribers.`)
      setBroadcastText('')
    } catch (e) {
      onError(errMsg(e))
    }
  }

  return (
    <section className="card">
      <div className="card-head">Post to channel · Broadcast</div>
      {note && <p className="hint">{note}</p>}
      <div className="form-row">
        <input placeholder="@channel or chat id" value={chatId} onChange={(e) => setChatId(e.target.value)} />
        <input placeholder="Text" value={postText} onChange={(e) => setPostText(e.target.value)} />
        <input placeholder="Image URL (optional)" value={imageUrl} onChange={(e) => setImageUrl(e.target.value)} />
        <button className="btn btn-primary" onClick={post} disabled={!chatId}>
          Post
        </button>
      </div>
      <div className="form-row" style={{ marginTop: 8 }}>
        <input placeholder="Broadcast message to subscribers" value={broadcastText} onChange={(e) => setBroadcastText(e.target.value)} />
        <button className="btn btn-ghost" onClick={broadcast} disabled={!broadcastText.trim()}>
          Broadcast
        </button>
      </div>
    </section>
  )
}
