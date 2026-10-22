import { useEffect, useRef, useState, type FormEvent } from 'react'
import { api, ApiError, type AskOut, type DocumentOut, type Health } from '../api'
import { displayName } from '../library'
import { formatDuration, type AskProgress } from '../stages'
import { Answer } from './Answer'
import { BidiText } from './common'
import { PlusIcon, SendIcon, SparkIcon, StopIcon } from './icons'
import { AskProgressCard } from './Progress'

interface Turn {
  id: number
  question: string
  scope: string
  progress: AskProgress
  res?: AskOut
  error?: string
  stopped?: boolean
}

const EXAMPLES = ['What is this document about?', 'اس دستاویز کا خلاصہ بتائیں', 'کمپنی کا نصب العین کیا ہے؟']

interface Props {
  docs: DocumentOut[]
  health: Health | null
  offline: boolean
  selected: number[]
  onClearSelection: () => void
  onNotice: (msg: string, kind?: 'error' | 'info') => void
}

function Avatar() {
  return (
    <span className="avatar" aria-hidden>
      <SparkIcon />
    </span>
  )
}

export function ChatPanel({ docs, health, offline, selected, onClearSelection, onNotice }: Props) {
  const [question, setQuestion] = useState('')
  const [turns, setTurns] = useState<Turn[]>([])
  const [asking, setAsking] = useState(false)
  const bottom = useRef<HTMLDivElement>(null)
  const abort = useRef<AbortController | null>(null)

  const ready = docs.filter((d) => d.status === 'ready')

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [turns])

  async function ask(e?: FormEvent, text?: string) {
    e?.preventDefault()
    const q = (text ?? question).trim()
    if (!q || asking) return
    if (!ready.length) {
      onNotice('No documents are ready yet. Upload a PDF and wait for it to finish indexing.', 'info')
      return
    }
    const scope = selected.length
      ? ready
          .filter((d) => selected.includes(d.id))
          .map((d) => d.filename)
          .join(', ')
      : 'All documents'
    const id = Date.now()
    const startedAt = performance.now()
    const update = (fn: (t: Turn) => Turn) => setTurns((ts) => ts.map((x) => (x.id === id ? fn(x) : x)))
    setTurns((t) => [...t, { id, question: q, scope, progress: { startedAt, steps: [] } }])
    setQuestion('')
    setAsking(true)
    const controller = new AbortController()
    abort.current = controller
    try {
      const ids = selected.length ? selected : null
      const res = await api
        .askStream(
          q,
          ids,
          (ev) =>
            update((t) => {
              const p = t.progress
              if (ev.type === 'step')
                return { ...t, progress: { ...p, steps: [...p.steps, { step: ev.step, at: performance.now() }] } }
              if (ev.type === 'candidates') return { ...t, progress: { ...p, candidates: ev.count } }
              if (ev.type === 'sources') return { ...t, progress: { ...p, sources: ev.sources } }
              return t
            }),
          controller.signal,
        )
        .catch((err) => {
          // an older backend without /ask/stream: answer without live progress
          if (err instanceof ApiError && err.message.startsWith('404')) return api.ask(q, ids)
          throw err
        })
      update((t) => ({ ...t, res }))
    } catch (err) {
      if (controller.signal.aborted) {
        update((t) => ({
          ...t,
          stopped: true,
          error: `Stopped after ${formatDuration(performance.now() - startedAt)}.`,
        }))
      } else {
        const msg = err instanceof ApiError ? err.message : String(err)
        update((t) => ({ ...t, error: msg }))
      }
    } finally {
      abort.current = null
      setAsking(false)
    }
  }

  return (
    <section className="chat pane">
      <header className="pane-head chat-head">
        <Avatar />
        <div className="chat-head-text">
          <div className="pane-title">AI Assistant</div>
          <div className={`chat-status ${offline ? 'is-bad' : ''}`}>
            <span className="sys-dot" aria-hidden />
            {offline ? 'Backend offline' : `RAG active${health ? ` · ${health.llm_model}` : ''}`}
          </div>
        </div>
        <button
          className="icon-btn"
          onClick={() => setTurns([])}
          disabled={asking || turns.length === 0}
          title="New conversation"
          aria-label="New conversation"
        >
          <PlusIcon width={18} height={18} />
        </button>
      </header>

      <div className="messages">
        <div className="msg msg-bot">
          <Avatar />
          <div className="bubble-bot">
            {ready.length ? (
              <>
                <p>
                  Hello! I answer questions from your documents and cite the page for every answer. I have{' '}
                  {ready.length === 1 ? 'indexed ' : `${ready.length} documents indexed, including `}
                  <span className="doc-link">{displayName(ready[0].filename)}</span>.
                </p>
                <p className="bubble-ur" dir="rtl">
                  اردو یا انگریزی میں سوال پوچھیں۔
                </p>
              </>
            ) : (
              <p>Hello! Upload a PDF on the left and I'll answer questions about it, citing the page each answer comes from.</p>
            )}
            {turns.length === 0 && ready.length > 0 && (
              <div className="examples">
                {EXAMPLES.map((ex) => (
                  <button key={ex} className="example" dir="auto" onClick={() => ask(undefined, ex)}>
                    {ex}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {turns.map((t) => (
          <div key={t.id} className="turn">
            <div className="msg msg-user">
              <div className="question-bubble">
                <BidiText text={t.question} />
                <div className="scope">{t.scope}</div>
              </div>
            </div>
            <div className="msg msg-bot">
              <Avatar />
              <div className="msg-body">
                {t.res ? (
                  <Answer res={t.res} />
                ) : t.error ? (
                  <div className={`notice ${t.stopped ? 'notice-info' : 'notice-error'}`}>{t.error}</div>
                ) : (
                  <AskProgressCard progress={t.progress} onStop={() => abort.current?.abort()} />
                )}
              </div>
            </div>
          </div>
        ))}
        <div ref={bottom} />
      </div>

      <form className="composer" onSubmit={ask}>
        {selected.length > 0 && (
          <div className="composer-scope">
            Searching {selected.length} selected document{selected.length > 1 ? 's' : ''}
            <button type="button" className="link" onClick={onClearSelection}>
              search all
            </button>
          </div>
        )}
        <div className="composer-box">
          <textarea
            dir="auto"
            value={question}
            placeholder="Ask a question about your documents… / اپنا سوال لکھیں"
            rows={1}
            maxLength={2000}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                ask()
              }
            }}
          />
          {asking ? (
            <button type="button" className="send-btn" onClick={() => abort.current?.abort()} title="Stop">
              <StopIcon />
            </button>
          ) : (
            <button className="send-btn" type="submit" disabled={!question.trim()} title="Send (Enter)">
              <SendIcon />
            </button>
          )}
        </div>
        <div className="composer-hint">Answers come only from your documents. Check the cited pages for important facts.</div>
      </form>
    </section>
  )
}
