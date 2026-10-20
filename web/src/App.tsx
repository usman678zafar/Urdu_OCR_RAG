import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { api, ApiError, type AskOut, type DocumentOut, type Health } from './api'
import { Answer } from './components/Answer'
import { BidiText, Spinner } from './components/common'
import { DocumentDetail } from './components/DocumentDetail'
import { Sidebar } from './components/Sidebar'

interface Turn {
  id: number
  question: string
  scope: string
  res?: AskOut
  error?: string
}

const EXAMPLES = ['بینظیر بھٹو پہلی بار وزیر اعظم کب بنیں؟', 'What is this document about?', 'اس کتاب کا مصنف کون ہے؟']

export default function App() {
  const [docs, setDocs] = useState<DocumentOut[]>([])
  const [health, setHealth] = useState<Health | null>(null)
  const [offline, setOffline] = useState(false)
  const [selected, setSelected] = useState<number[]>([])
  const [question, setQuestion] = useState('')
  const [turns, setTurns] = useState<Turn[]>([])
  const [asking, setAsking] = useState(false)
  const [detailId, setDetailId] = useState<number | null>(null)
  const [notice, setNotice] = useState<{ msg: string; kind: 'error' | 'info' } | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const bottom = useRef<HTMLDivElement>(null)

  const refresh = useCallback(async () => {
    try {
      const [d, h] = await Promise.all([api.listDocuments(), api.health()])
      setDocs(d)
      setHealth(h)
      setOffline(false)
      // drop selections for documents that are gone or no longer ready
      setSelected((s) => s.filter((id) => d.some((x) => x.id === id && x.status === 'ready')))
    } catch {
      setOffline(true)
    }
  }, [])

  // Poll quickly while something is processing, slowly otherwise
  const busy = docs.some((d) => d.status !== 'ready' && d.status !== 'failed')
  useEffect(() => {
    refresh()
    const t = setInterval(refresh, busy ? 2500 : 15000)
    return () => clearInterval(t)
  }, [refresh, busy])

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: 'smooth' })
  }, [turns])

  useEffect(() => {
    if (!notice) return
    const t = setTimeout(() => setNotice(null), 6000)
    return () => clearTimeout(t)
  }, [notice])

  const ready = docs.filter((d) => d.status === 'ready')

  async function ask(e?: FormEvent) {
    e?.preventDefault()
    const q = question.trim()
    if (!q || asking) return
    if (!ready.length) {
      setNotice({ msg: 'No documents are ready yet. Upload a PDF and wait for it to finish indexing.', kind: 'info' })
      return
    }
    const scope = selected.length
      ? ready.filter((d) => selected.includes(d.id)).map((d) => d.filename).join(', ')
      : 'All documents'
    const id = Date.now()
    setTurns((t) => [...t, { id, question: q, scope }])
    setQuestion('')
    setAsking(true)
    try {
      const res = await api.ask(q, selected.length ? selected : null)
      setTurns((t) => t.map((x) => (x.id === id ? { ...x, res } : x)))
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : String(err)
      setTurns((t) => t.map((x) => (x.id === id ? { ...x, error: msg } : x)))
    } finally {
      setAsking(false)
    }
  }

  return (
    <div className={`app ${sidebarOpen ? 'sidebar-open' : ''}`}>
      <Sidebar
        docs={docs}
        selected={selected}
        onToggle={(id) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]))}
        onChanged={refresh}
        onOpen={setDetailId}
        onNotice={(msg, kind = 'error') => setNotice({ msg, kind })}
      />
      <div className="scrim" onClick={() => setSidebarOpen(false)} />

      <main className="main">
        <header className="topbar">
          <button className="icon-btn menu-btn" onClick={() => setSidebarOpen((o) => !o)} aria-label="Documents">
            ☰
          </button>
          <div className="topbar-title">Ask your documents</div>
          <div className="topbar-status">
            {offline ? (
              <span className="dot dot-bad">Backend offline</span>
            ) : health ? (
              <>
                <span className="dot dot-ok">
                  {health.ready}/{health.documents} ready
                </span>
                <span className="chip" title="Answering model">{health.llm_model}</span>
                <span className="chip" title="OCR engine">OCR: {health.ocr_engine}</span>
              </>
            ) : null}
          </div>
        </header>

        {notice && <div className={`toast notice notice-${notice.kind}`}>{notice.msg}</div>}

        <section className="conversation">
          {turns.length === 0 ? (
            <div className="welcome">
              <h1>
                Urdu Document Q&amp;A
                <span className="welcome-ur" dir="rtl">
                  اپنی دستاویزات سے پوچھیں
                </span>
              </h1>
              <p className="muted">
                Upload Urdu or English PDFs, then ask questions. Every answer cites the file, page and passage it
                came from.
              </p>
              <div className="examples">
                {EXAMPLES.map((ex) => (
                  <button key={ex} className="example" dir="auto" onClick={() => setQuestion(ex)}>
                    {ex}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            turns.map((t) => (
              <div key={t.id} className="turn">
                <div className="question-bubble">
                  <BidiText text={t.question} />
                  <div className="scope">{t.scope}</div>
                </div>
                {t.res ? (
                  <Answer res={t.res} />
                ) : t.error ? (
                  <div className="notice notice-error">{t.error}</div>
                ) : (
                  <div className="thinking">
                    <Spinner /> Searching documents and writing an answer…
                  </div>
                )}
              </div>
            ))
          )}
          <div ref={bottom} />
        </section>

        <form className="composer" onSubmit={ask}>
          {selected.length > 0 && (
            <div className="composer-scope">
              Searching {selected.length} selected document{selected.length > 1 ? 's' : ''}
              <button type="button" className="link" onClick={() => setSelected([])}>
                search all
              </button>
            </div>
          )}
          <div className="composer-box">
            <textarea
              dir="auto"
              value={question}
              placeholder="Ask a question… / اپنا سوال لکھیں"
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
            <button className="btn btn-primary" type="submit" disabled={!question.trim() || asking}>
              {asking ? <Spinner /> : 'Ask'}
            </button>
          </div>
          <div className="composer-hint muted">Enter to send · Shift+Enter for a new line</div>
        </form>
      </main>

      {detailId !== null && (
        <DocumentDetail id={detailId} onClose={() => setDetailId(null)} onChanged={refresh} />
      )}
    </div>
  )
}
