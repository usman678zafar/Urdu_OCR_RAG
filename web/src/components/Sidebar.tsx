import { useRef, useState, type DragEvent } from 'react'
import { api, ApiError, type DocumentOut } from '../api'
import { Spinner, StatusBadge } from './common'

interface Props {
  docs: DocumentOut[]
  selected: number[]
  onToggle: (id: number) => void
  onChanged: () => void
  onOpen: (id: number) => void
  onNotice: (msg: string, kind?: 'error' | 'info') => void
}

export function Sidebar({ docs, selected, onToggle, onChanged, onOpen, onNotice }: Props) {
  const input = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState<string[]>([])
  const [dragging, setDragging] = useState(false)

  async function upload(files: FileList | File[]) {
    const pdfs = Array.from(files).filter((f) => f.name.toLowerCase().endsWith('.pdf'))
    if (pdfs.length < Array.from(files).length) onNotice('Only PDF files are accepted.', 'error')
    for (const f of pdfs) {
      setUploading((u) => [...u, f.name])
      try {
        const res = await api.upload(f)
        if (res.duplicate) onNotice(`${f.name} was already uploaded.`, 'info')
      } catch (e) {
        onNotice(e instanceof ApiError ? `${f.name}: ${e.message}` : String(e), 'error')
      } finally {
        setUploading((u) => u.filter((n) => n !== f.name))
        onChanged()
      }
    }
  }

  function onDrop(e: DragEvent) {
    e.preventDefault()
    setDragging(false)
    upload(e.dataTransfer.files)
  }

  async function remove(d: DocumentOut) {
    if (!confirm(`Delete "${d.filename}" and its index?`)) return
    try {
      await api.remove(d.id)
    } catch (e) {
      onNotice(String(e instanceof Error ? e.message : e), 'error')
    }
    onChanged()
  }

  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="brand-mark">ق</span>
        <div>
          <div className="brand-name">Urdu Doc Q&amp;A</div>
          <div className="brand-sub">دستاویزات سے سوال جواب</div>
        </div>
      </div>

      <div
        className={`dropzone ${dragging ? 'dragging' : ''}`}
        onClick={() => input.current?.click()}
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        role="button"
        tabIndex={0}
      >
        <div className="dropzone-icon">⬆</div>
        <div className="dropzone-title">Drop PDFs here or click to upload</div>
        <div className="dropzone-sub">Urdu or English · typed or scanned</div>
        <input
          ref={input}
          type="file"
          accept="application/pdf,.pdf"
          multiple
          hidden
          onChange={(e) => {
            if (e.target.files) upload(e.target.files)
            e.target.value = ''
          }}
        />
      </div>

      {uploading.map((n) => (
        <div key={n} className="uploading">
          <Spinner /> Uploading {n}…
        </div>
      ))}

      <div className="doc-list-head">
        <span>Documents</span>
        {selected.length > 0 && <span className="muted">{selected.length} selected</span>}
      </div>

      {docs.length === 0 && <div className="empty-docs">No documents yet.</div>}

      <ul className="doc-list">
        {docs.map((d) => {
          const busy = d.status !== 'ready' && d.status !== 'failed'
          const pct = d.page_count ? Math.round((d.pages_done / d.page_count) * 100) : 0
          const isSel = selected.includes(d.id)
          return (
            <li key={d.id} className={`doc ${isSel ? 'doc-selected' : ''}`}>
              <div className="doc-row">
                <input
                  type="checkbox"
                  checked={isSel}
                  disabled={d.status !== 'ready'}
                  onChange={() => onToggle(d.id)}
                  title="Limit questions to this document"
                />
                <button className="doc-name" onClick={() => onOpen(d.id)} title={d.filename}>
                  {d.filename}
                </button>
              </div>
              <div className="doc-meta">
                <StatusBadge status={d.status} />
                <span className="muted">{d.page_count} pages</span>
                <span className="doc-actions">
                  <button className="icon-btn" onClick={() => remove(d)} disabled={busy} title="Delete">
                    🗑
                  </button>
                </span>
              </div>
              {busy && (
                <div className="progress" title={`${d.pages_done}/${d.page_count} pages`}>
                  <div
                    className={`progress-bar ${d.status === 'indexing' ? 'indeterminate' : ''}`}
                    style={{ width: d.status === 'indexing' ? undefined : `${pct}%` }}
                  />
                  <span className="progress-label">
                    {d.status === 'indexing'
                      ? 'Building embeddings…'
                      : `OCR ${d.pages_done}/${d.page_count}${d.pages_failed ? `, ${d.pages_failed} failed` : ''}`}
                  </span>
                </div>
              )}
              {d.error && <div className={d.status === 'failed' ? 'doc-error' : 'doc-warn'}>{d.error}</div>}
            </li>
          )
        })}
      </ul>
    </aside>
  )
}
