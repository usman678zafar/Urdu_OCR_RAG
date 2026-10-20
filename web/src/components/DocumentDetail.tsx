import { useEffect, useState } from 'react'
import { api, imageSrc, type DocumentDetailOut } from '../api'
import { Modal, Spinner, StatusBadge } from './common'

export function DocumentDetail({
  id,
  onClose,
  onChanged,
}: {
  id: number
  onClose: () => void
  onChanged: () => void
}) {
  const [doc, setDoc] = useState<DocumentDetailOut | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [page, setPage] = useState<number | null>(null)

  useEffect(() => {
    api.getDocument(id).then(setDoc, (e) => setError(String(e.message ?? e)))
  }, [id])

  async function reprocess() {
    if (!confirm('Read and index this document again? This can take a while for scanned books.')) return
    await api.reprocess(id)
    onChanged()
    onClose()
  }

  const ocrPages = doc?.pages.filter((p) => p.ocr_confidence !== null) ?? []
  const avgConf = ocrPages.length
    ? ocrPages.reduce((s, p) => s + (p.ocr_confidence ?? 0), 0) / ocrPages.length
    : null
  const lowCount = doc?.pages.filter((p) => p.low_confidence).length ?? 0
  const current = doc?.pages.find((p) => p.page_no === page)

  return (
    <Modal onClose={onClose} wide>
      {error && <div className="notice notice-error">{error}</div>}
      {!doc && !error && (
        <div className="center">
          <Spinner />
        </div>
      )}
      {doc && (
        <div className="detail">
          <header className="detail-head">
            <h2 title={doc.filename}>{doc.filename}</h2>
            <div className="detail-stats">
              <StatusBadge status={doc.status} />
              <span>{doc.page_count} pages</span>
              {avgConf !== null && <span>OCR confidence {(avgConf * 100).toFixed(0)}%</span>}
              {lowCount > 0 && <span className="warn">{lowCount} low-confidence pages</span>}
              {(doc.status === 'ready' || doc.status === 'failed') && (
                <button className="btn btn-ghost" onClick={reprocess}>
                  Reprocess
                </button>
              )}
            </div>
          </header>
          <div className="detail-body">
            <div className="page-grid">
              {doc.pages.map((p) => (
                <button
                  key={p.page_no}
                  className={`page-tile ${p.low_confidence ? 'low' : ''} ${page === p.page_no ? 'active' : ''}`}
                  onClick={() => setPage(p.page_no)}
                  title={p.reason ?? ''}
                >
                  <span className="page-no">{p.page_no}</span>
                  <span className="page-method">{p.method}</span>
                  {p.ocr_confidence !== null && (
                    <span className="page-conf">{Math.round(p.ocr_confidence * 100)}%</span>
                  )}
                </button>
              ))}
            </div>
            <div className="page-preview">
              {current ? (
                <>
                  <div className="page-preview-meta">
                    Page {current.page_no} · {current.method}
                    {current.reason ? ` · ${current.reason}` : ''} · {current.text_chars} chars
                  </div>
                  <img src={imageSrc(current.image_url)} alt={`Page ${current.page_no}`} />
                </>
              ) : (
                <div className="muted center">Select a page to preview it.</div>
              )}
            </div>
          </div>
        </div>
      )}
    </Modal>
  )
}
