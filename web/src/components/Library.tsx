import { useRef, useState, type DragEvent } from 'react'
import { api, ApiError, type DocumentOut } from '../api'
import { displayName, FILTERS, type LibraryFilter } from '../library'
import { Spinner, StatusBadge } from './common'
import { FileIcon, InfoIcon, MenuIcon, PlusIcon, SearchIcon, TrashIcon, UploadIcon } from './icons'

interface Props {
  docs: DocumentOut[]
  filter: LibraryFilter
  selected: number[]
  onToggle: (id: number) => void
  onSelect: (ids: number[]) => void
  onChanged: () => void
  onOpen: (id: number) => void
  onNotice: (msg: string, kind?: 'error' | 'info') => void
  onMenu: () => void
}

/** "Today", "Yesterday" or a short date. SQLite timestamps are UTC without a zone. */
function addedLabel(ts: string): string {
  const d = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(ts) ? ts : ts.replace(' ', 'T') + 'Z')
  if (Number.isNaN(d.getTime())) return ts
  const day = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime()
  const diff = Math.round((day(new Date()) - day(d)) / 86_400_000)
  if (diff === 0) return 'Today'
  if (diff === 1) return 'Yesterday'
  return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: diff > 300 ? 'numeric' : undefined })
}

export function Library({ docs, filter, selected, onToggle, onSelect, onChanged, onOpen, onNotice, onMenu }: Props) {
  const input = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState<string[]>([])
  const [dragging, setDragging] = useState(false)
  const [query, setQuery] = useState('')

  const active = FILTERS.find((f) => f.key === filter) ?? FILTERS[0]
  const q = query.trim().toLowerCase()
  const shown = docs.filter((d) => active.match(d) && (!q || d.filename.toLowerCase().includes(q)))
  const selectable = shown.filter((d) => d.status === 'ready')
  const allSelected = selectable.length > 0 && selectable.every((d) => selected.includes(d.id))

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

  const pick = () => input.current?.click()

  return (
    <section className="library pane">
      <div className="pane-head">
        <button className="icon-btn nav-toggle" onClick={onMenu} aria-label="Open navigation">
          <MenuIcon />
        </button>
        <h2 className="pane-title">Upload documents</h2>
      </div>

      <div className="library-body">
        <div
          className={`dropzone ${dragging ? 'dragging' : ''}`}
          onClick={pick}
          onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && pick()}
          onDragOver={(e) => {
            e.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          role="button"
          tabIndex={0}
        >
          <span className="dropzone-icon">
            <UploadIcon width={20} height={20} />
          </span>
          <div className="dropzone-title">Click to upload or drag and drop</div>
          <div className="dropzone-sub">PDF · Urdu or English · typed or scanned</div>
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

        <div className="toolbar">
          <nav className="crumbs" aria-label="Breadcrumb">
            <span>Home</span>
            <span aria-hidden>›</span>
            <strong>{filter === 'all' ? 'Knowledge base' : active.label}</strong>
          </nav>
          <label className="search">
            <SearchIcon />
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Filter by name" />
          </label>
          <button className="btn btn-dark" onClick={pick}>
            <PlusIcon /> Add new
          </button>
        </div>

        <div className="doc-table" role="table" aria-label="Documents">
          <div className="doc-tr doc-th" role="row">
            <span role="columnheader">
              <input
                type="checkbox"
                checked={allSelected}
                disabled={!selectable.length}
                onChange={() =>
                  onSelect(
                    allSelected
                      ? selected.filter((id) => !selectable.some((d) => d.id === id))
                      : [...new Set([...selected, ...selectable.map((d) => d.id)])],
                  )
                }
                title="Select all ready documents shown"
                aria-label="Select all"
              />
            </span>
            <span role="columnheader">File name</span>
            <span role="columnheader">Status</span>
            <span role="columnheader" className="num">
              Pages
            </span>
            <span role="columnheader" className="col-added">
              Added
            </span>
            <span role="columnheader" aria-label="Actions" />
          </div>

          {uploading.map((n) => (
            <div key={n} className="doc-tr doc-row-uploading" role="row">
              <span />
              <span className="doc-file">
                <span className="doc-icon">
                  <Spinner />
                </span>
                <span className="doc-name">{displayName(n)}</span>
              </span>
              <span className="muted">Uploading…</span>
            </div>
          ))}

          {shown.map((d) => {
            const busy = d.status !== 'ready' && d.status !== 'failed'
            const pct = d.page_count ? Math.round((d.pages_done / d.page_count) * 100) : 0
            const isSel = selected.includes(d.id)
            return (
              <div key={d.id} className={`doc-tr ${isSel ? 'is-selected' : ''}`} role="row">
                <span role="cell">
                  <input
                    type="checkbox"
                    checked={isSel}
                    disabled={d.status !== 'ready'}
                    onChange={() => onToggle(d.id)}
                    title="Limit questions to this document"
                    aria-label={`Select ${d.filename}`}
                  />
                </span>
                <span role="cell" className="doc-file">
                  <span className={`doc-icon doc-icon-${d.status}`}>
                    <FileIcon />
                  </span>
                  <span className="doc-file-text">
                    <button className="doc-name" onClick={() => onOpen(d.id)} title={d.filename}>
                      {displayName(d.filename)}
                    </button>
                    {busy && (
                      <span className="progress" title={`${d.pages_done}/${d.page_count} pages`}>
                        <span
                          className={`progress-bar ${d.status === 'indexing' ? 'indeterminate' : ''}`}
                          style={{ width: d.status === 'indexing' ? undefined : `${pct}%` }}
                        />
                        <span className="progress-label">
                          {d.status === 'indexing'
                            ? 'Building embeddings…'
                            : `OCR ${d.pages_done}/${d.page_count}${d.pages_failed ? `, ${d.pages_failed} failed` : ''}`}
                        </span>
                      </span>
                    )}
                    {d.error && (
                      <span className={d.status === 'failed' ? 'doc-error' : 'doc-warn'} title={d.error}>
                        {d.error}
                      </span>
                    )}
                  </span>
                </span>
                <span role="cell">
                  <StatusBadge status={d.status} />
                </span>
                <span role="cell" className="num">
                  {d.page_count}
                </span>
                <span role="cell" className="col-added muted">
                  {addedLabel(d.uploaded_at)}
                </span>
                <span role="cell" className="row-actions">
                  <button className="icon-btn" onClick={() => onOpen(d.id)} title="Pages and OCR details">
                    <InfoIcon />
                  </button>
                  <button className="icon-btn danger" onClick={() => remove(d)} disabled={busy} title="Delete">
                    <TrashIcon />
                  </button>
                </span>
              </div>
            )
          })}

          {shown.length === 0 && !uploading.length && (
            <div className="table-empty">
              <FileIcon width={22} height={22} />
              <div>{docs.length ? 'No documents match.' : 'No documents yet'}</div>
              <div className="muted">
                {docs.length ? 'Try another filter or name.' : 'Upload a PDF to start asking questions.'}
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  )
}
